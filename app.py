import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title='BeOne Gym Assistant', page_icon='🏋️', layout='wide')
st.title('🏋️ BeOne Gym Assistant')
st.caption('Tus clases recomendadas, de lunes a domingo')

DAYS = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes','Saturday':'Sábado','Sunday':'Domingo'}
API = 'https://trainingymapp.com/webtouch/api/usuarios/reservas/centers/2394/getschedulesnotauth'
EXCLUIDAS = {'PILATES REFORMER CLUB'}
PUNTOS_INICIALES = {'PILATES': 3, 'YOGA': 2, 'BODYPUMP': 1}

@st.cache_data(ttl=900, show_spinner=False)
def descargar_clases(lunes_str):
    lunes = datetime.strptime(lunes_str, '%Y-%m-%d').date()
    domingo = lunes + timedelta(days=6)
    periodos = [(lunes, lunes + timedelta(days=3)), (lunes + timedelta(days=4), domingo)]
    clases, vistos = [], set()
    for inicio, fin in periodos:
        respuesta = requests.get(API, params={'startDateTime': str(inicio), 'endDateTime': str(fin)}, timeout=20)
        respuesta.raise_for_status()
        for dia in respuesta.json().get('calendar', []):
            fecha = dia.get('dateProgram')
            if not fecha:
                continue
            for clase in dia.get('schedules', []):
                identificador = clase.get('id')
                if identificador in vistos:
                    continue
                vistos.add(identificador)
                actividad = clase.get('activity') or {}
                sala = (clase.get('room') or {}).get('room') or 'Sin especificar'
                nombre = (actividad.get('name') or '').strip().upper()
                if not nombre or not clase.get('timeStart') or not clase.get('timeEnd'):
                    continue
                clases.append({'fecha': fecha, 'nombre': nombre, 'sala': sala, 'inicio': clase['timeStart'][:5], 'fin': clase['timeEnd'][:5]})
    return clases


hoy = datetime.now(ZoneInfo('Europe/Madrid')).date()
lunes_actual = hoy - timedelta(days=hoy.weekday())

semana_elegida = st.selectbox(
    "📅 ¿Qué semana quieres consultar?",
    options=list(range(6)),
    format_func=lambda n: (
        "Esta semana" if n == 0
        else "Próxima semana" if n == 1
        else f"Dentro de {n} semanas"
    )
)

lunes = lunes_actual + timedelta(weeks=semana_elegida)
domingo = lunes + timedelta(days=6)

st.subheader(
    f'📅 Semana del {lunes.strftime("%d/%m")} '
    f'al {domingo.strftime("%d/%m/%Y")}'
)

if st.button('🔄 Actualizar mi semana', type='primary'):
    descargar_clases.clear()

try:
    with st.spinner('Consultando clases de BeOne…'):
        clases = descargar_clases(str(lunes))
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f'No se pudieron consultar los horarios de BeOne: {exc}')
    st.stop()

# El catálogo procede de las actividades realmente programadas esta semana.
actividades_disponibles = sorted({c['nombre'] for c in clases if c['nombre'] not in EXCLUIDAS})
seleccion_inicial = [a for a in PUNTOS_INICIALES if a in actividades_disponibles]

with st.sidebar:
    st.header('Mis preferencias')
    favoritas = st.multiselect(
        'Actividades que quiero hacer',
        options=actividades_disponibles,
        default=seleccion_inicial,
        help='Se muestran las actividades que aparecen en el horario de esta semana.'
    )
    st.caption(f'{len(actividades_disponibles)} actividades distintas en el horario semanal. Pilates Reformer Club está excluido por defecto.')
    st.subheader('Puntúa tus actividades (1–5)')
    puntuaciones = {}
    for actividad in favoritas:
        puntuaciones[actividad] = st.slider(
            f'⭐ {actividad}', min_value=1, max_value=5,
            value=PUNTOS_INICIALES.get(actividad, 3), key=f'puntos_{actividad}'
        )
    st.header('Mi disponibilidad')
    st.caption('Configura los días y horas en los que podrías asistir.')
    disponibilidad = {}
    for day in DAYS:
        with st.expander(DAYS[day], expanded=day in ['Monday','Tuesday','Wednesday','Thursday','Friday']):
            activo = st.checkbox('Disponible', value=day in ['Monday','Tuesday','Wednesday','Thursday','Friday'], key=f'active_{day}')
            inicio = st.time_input('Desde', value=datetime.strptime('18:00' if day != 'Friday' else '17:00','%H:%M').time(), key=f'from_{day}')
            fin = st.time_input('Hasta', value=datetime.strptime('21:30','%H:%M').time(), key=f'to_{day}')
            disponibilidad[day] = (inicio.strftime('%H:%M'), fin.strftime('%H:%M')) if activo else None

recomendaciones = []
for clase in clases:
    nombre = clase['nombre']
    if nombre not in puntuaciones:
        continue
    dia = datetime.strptime(clase['fecha'], '%Y-%m-%d').strftime('%A')
    horario = disponibilidad.get(dia)
    if horario is None:
        continue
    if horario[0] <= clase['inicio'] and clase['fin'] <= horario[1]:
        recomendaciones.append({**clase, 'Puntos': puntuaciones[nombre]})

st.metric('Clases que encajan contigo', len(recomendaciones))
if not recomendaciones:
    st.info('No hay clases que coincidan con tus preferencias y horarios esta semana.')
else:
    for fecha in sorted({c['fecha'] for c in recomendaciones}):
        dia = datetime.strptime(fecha,'%Y-%m-%d')
        st.markdown(f'### 📅 {DAYS[dia.strftime("%A")]} {dia.strftime("%d/%m")}')
        grupo = sorted((c for c in recomendaciones if c['fecha']==fecha), key=lambda c:(-c['Puntos'],c['inicio']))
        
        df = pd.DataFrame(grupo).rename(
            columns={
                'nombre': 'Actividad',
                'inicio': 'Inicio',
                'fin': 'Fin',
                'sala': 'Sala'
            }
        )[['Actividad', 'Inicio', 'Fin', 'Sala', 'Puntos']]
        def color_puntos(valor):
            if valor >= 4: return 'background-color: #d4edda; color: #155724'
            if valor == 3: return 'background-color: #fff3cd; color: #856404'
            return 'background-color: #f8d7da; color: #721c24'
        st.dataframe(df.style.map(color_puntos, subset=['Puntos']), hide_index=True, use_container_width=True)

st.caption('Actividades disponibles según la programación de esta semana. Confirma las reservas en BeOne. Las preferencias no se guardan permanentemente todavía.')
