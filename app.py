import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title='BeOne Gym Assistant', page_icon='🏋️', layout='wide')
st.title('🏋️ BeOne Gym Assistant')
st.caption('Tus clases recomendadas, de lunes a domingo')

DAYS = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes','Saturday':'Sábado','Sunday':'Domingo'}
ACTIVITIES = ['PILATES', 'YOGA', 'BODYPUMP']
API = 'https://trainingymapp.com/webtouch/api/usuarios/reservas/centers/2394/getschedulesnotauth'

with st.sidebar:
    st.header('Mis preferencias')
    favoritas = st.multiselect('Actividades favoritas', ACTIVITIES, default=ACTIVITIES)
    st.caption('Pilates Reformer Club queda excluido (actividad de pago).')
    puntuaciones = {a: st.slider(f'Puntos: {a.title()}', 1, 5, v) for a, v in [('PILATES',3),('YOGA',2),('BODYPUMP',1)]}
    st.header('Mi disponibilidad')
    st.caption('Configura los días y horas en los que podrías asistir.')
    disponibilidad = {}
    for day in DAYS:
        with st.expander(DAYS[day], expanded=day in ['Monday','Tuesday','Wednesday','Thursday','Friday']):
            activo = st.checkbox('Disponible', value=day in ['Monday','Tuesday','Wednesday','Thursday','Friday'], key=f'active_{day}')
            inicio = st.time_input('Desde', value=datetime.strptime('18:00' if day != 'Friday' else '17:00','%H:%M').time(), key=f'from_{day}')
            fin = st.time_input('Hasta', value=datetime.strptime('21:30','%H:%M').time(), key=f'to_{day}')
            disponibilidad[day] = (inicio.strftime('%H:%M'), fin.strftime('%H:%M')) if activo else None

@st.cache_data(ttl=900, show_spinner=False)
def descargar_clases(lunes_str):
    lunes = datetime.strptime(lunes_str, '%Y-%m-%d').date()
    domingo = lunes + timedelta(days=6)
    periodos = [(lunes, lunes+timedelta(days=3)), (lunes+timedelta(days=4), domingo)]
    clases, vistos = [], set()
    for inicio, fin in periodos:
        r = requests.get(API, params={'startDateTime':str(inicio),'endDateTime':str(fin)}, timeout=20)
        r.raise_for_status()
        for dia in r.json().get('calendar', []):
            fecha = dia.get('dateProgram')
            if not fecha:
                continue
            for clase in dia.get('schedules', []):
                identificador = clase.get('id')
                if identificador in vistos:
                    continue
                vistos.add(identificador)
                actividad = clase.get('activity') or {}
                if not actividad.get('name') or not clase.get('timeStart') or not clase.get('timeEnd'):
                    continue
                clases.append({'fecha':fecha,'nombre':actividad['name'],'inicio':clase['timeStart'][:5],'fin':clase['timeEnd'][:5]})
    return clases

hoy = datetime.now(ZoneInfo('Europe/Madrid')).date()
lunes = hoy - timedelta(days=hoy.weekday())
domingo = lunes + timedelta(days=6)
st.subheader(f'📅 Semana del {lunes.strftime("%d/%m")} al {domingo.strftime("%d/%m/%Y")}')
if st.button('🔄 Actualizar mi semana', type='primary'):
    descargar_clases.clear()

try:
    with st.spinner('Consultando clases de BeOne…'):
        clases = descargar_clases(str(lunes))
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f'No se pudieron consultar los horarios de BeOne: {exc}')
    st.stop()

recomendaciones = []
for clase in clases:
    nombre = clase['nombre'].upper()
    if not any(a in nombre for a in favoritas):
        continue
    if 'PILATES REFORMER CLUB' in nombre:
        continue
    dia = datetime.strptime(clase['fecha'], '%Y-%m-%d').strftime('%A')
    horario = disponibilidad.get(dia)
    if horario is None:
        continue
    if horario[0] <= clase['inicio'] and clase['fin'] <= horario[1]:
        puntos = next((puntuaciones[a] for a in favoritas if a in nombre), 0)
        recomendaciones.append({**clase, 'Puntos':puntos})

st.metric('Clases que encajan contigo', len(recomendaciones))
if not recomendaciones:
    st.info('No hay clases que coincidan con tus preferencias y horarios esta semana.')
else:
    for fecha in sorted({c['fecha'] for c in recomendaciones}):
        dia = datetime.strptime(fecha,'%Y-%m-%d')
        st.markdown(f'### 📅 {DAYS[dia.strftime("%A")]} {dia.strftime("%d/%m")}')
        grupo = sorted((c for c in recomendaciones if c['fecha']==fecha), key=lambda c:(-c['Puntos'],c['fin']))
        df = pd.DataFrame(grupo).rename(columns={'nombre':'Actividad','inicio':'Inicio','fin':'Fin'})[['Actividad','Inicio','Fin','Puntos']]
        def color_puntos(valor):
            if valor >= 3: return 'background-color: #d4edda; color: #155724'
            if valor == 2: return 'background-color: #fff3cd; color: #856404'
            return 'background-color: #f8d7da; color: #721c24'
        st.dataframe(df.style.map(color_puntos, subset=['Puntos']), hide_index=True, use_container_width=True)

st.caption('Los horarios son informativos; confirma las clases y las reservas en BeOne. Las preferencias se restablecen al recargar la aplicación.')
