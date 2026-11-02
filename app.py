import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title='BeOne Gym Assistant', page_icon='🏋️', layout='wide')

DAYS = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
API = 'https://trainingymapp.com/webtouch/api/usuarios/reservas/centers/2394/getschedulesnotauth'
EXCLUIDAS = {'PILATES REFORMER CLUB'}
PUNTOS_INICIALES = {'PILATES': 3, 'YOGA': 2, 'BODYPUMP': 1}

# Esta aplicación es personal. La contraseña impide que los visitantes de la URL
# puedan leer o modificar el historial mediante la clave privada del servidor.
required_secrets = ('SUPABASE_URL', 'SUPABASE_KEY', 'APP_PASSWORD')
missing = [name for name in required_secrets if not st.secrets.get(name)]
if missing:
    st.error('Faltan secretos en Streamlit: ' + ', '.join(missing))
    st.info('Configura estos valores en Streamlit Community Cloud → Settings → Secrets. Nunca los publiques en GitHub.')
    st.stop()

if not st.session_state.get('authenticated', False):
    st.title('🔒 BeOne Gym Assistant')
    password = st.text_input('Contraseña de acceso', type='password')
    if st.button('Entrar', type='primary'):
        import hmac
        if hmac.compare_digest(password, str(st.secrets['APP_PASSWORD'])):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error('Contraseña incorrecta.')
    st.stop()

@st.cache_resource(show_spinner=False)
def db_client(url, key):
    return create_client(url, key)

try:
    db = db_client(st.secrets['SUPABASE_URL'], st.secrets['SUPABASE_KEY'])
except Exception as exc:
    st.error(f'No se pudo iniciar la conexión con Supabase: {exc}')
    st.stop()


def registros_semana(lunes):
    domingo = lunes + timedelta(days=6)
    result = (db.table('class_decisions')
              .select('class_id,class_date,activity,start_time,end_time,room,selected,attended')
              .gte('class_date', str(lunes))
              .lte('class_date', str(domingo))
              .execute())
    return {r['class_id']: r for r in (result.data or [])}


def guardar_decision(clase, seleccionada):
    identificador = f"{clase['fecha']}|{clase['id']}"
    payload = {
        'class_id': identificador,
        'class_date': clase['fecha'],
        'activity': clase['nombre'],
        'start_time': clase['inicio'],
        'end_time': clase['fin'],
        'room': clase['sala'],
        'selected': bool(seleccionada),
        'updated_at': datetime.now(ZoneInfo('Europe/Madrid')).isoformat(),
    }
    # No modificamos attended: una selección posterior no borra la asistencia confirmada.
    db.table('class_decisions').upsert(payload, on_conflict='class_id').execute()


def guardar_asistencia(class_id, valor):
    # None = pendiente; True = asistí; False = no asistí.
    db.table('class_decisions').update({
        'attended': valor,
        'updated_at': datetime.now(ZoneInfo('Europe/Madrid')).isoformat(),
    }).eq('class_id', class_id).execute()


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
                actividad = clase.get('activity') or {}
                sala = (clase.get('room') or {}).get('room') or 'Sin especificar'
                nombre = (actividad.get('name') or '').strip().upper()
                if not nombre or not clase.get('timeStart') or not clase.get('timeEnd'):
                    continue
                identificador = clase.get('id')
                if identificador is None:
                    identificador = f"{fecha}|{clase.get('timeStart')}|{nombre}|{sala}"
                unique_id = f'{fecha}|{identificador}'
                if unique_id in vistos:
                    continue
                vistos.add(unique_id)
                clases.append({
                    'id': str(identificador), 'fecha': fecha, 'nombre': nombre,
                    'sala': sala, 'inicio': clase['timeStart'][:5], 'fin': clase['timeEnd'][:5],
                })
    return clases


st.title('🏋️ BeOne Gym Assistant')
st.caption('Tus clases recomendadas, de lunes a domingo')
hoy = datetime.now(ZoneInfo('Europe/Madrid')).date()
lunes_actual = hoy - timedelta(days=hoy.weekday())
semana_elegida = st.selectbox(
    '📅 ¿Qué semana quieres consultar?',
    options=list(range(6)),
    format_func=lambda n: 'Esta semana' if n == 0 else 'Próxima semana' if n == 1 else f'Dentro de {n} semanas',
)
lunes = lunes_actual + timedelta(weeks=semana_elegida)
domingo = lunes + timedelta(days=6)
st.subheader(f'📅 Semana del {lunes.strftime("%d/%m")} al {domingo.strftime("%d/%m/%Y")}')
if st.button('🔄 Actualizar mi semana', type='primary'):
    descargar_clases.clear()

try:
    with st.spinner('Consultando clases de BeOne…'):
        clases = descargar_clases(str(lunes))
    guardadas = registros_semana(lunes)
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f'No se pudieron consultar los horarios de BeOne: {exc}')
    st.stop()
except Exception as exc:
    st.error(f'No se pudieron consultar tus elecciones en Supabase: {exc}')
    st.stop()

actividades_disponibles = sorted({c['nombre'] for c in clases if c['nombre'] not in EXCLUIDAS})
seleccion_inicial = [a for a in PUNTOS_INICIALES if a in actividades_disponibles]
with st.sidebar:
    st.header('Mis preferencias')
    favoritas = st.multiselect(
        'Actividades que quiero hacer', options=actividades_disponibles,
        default=seleccion_inicial,
        help='Se muestran las actividades que aparecen en el horario de esta semana.',
    )
    st.caption(f'{len(actividades_disponibles)} actividades distintas en el horario semanal. Pilates Reformer Club está excluido por defecto.')
    st.subheader('Puntúa tus actividades (1–5)')
    puntuaciones = {}
    for actividad in favoritas:
        puntuaciones[actividad] = st.slider(
            f'⭐ {actividad}', min_value=1, max_value=5,
            value=PUNTOS_INICIALES.get(actividad, 3), key=f'puntos_{actividad}',
        )
    st.header('Mi disponibilidad')
    st.caption('Configura los días y horas en los que podrías asistir.')
    disponibilidad = {}
    for day in DAYS:
        with st.expander(DAYS[day], expanded=day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']):
            activo = st.checkbox('Disponible', value=day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'], key=f'active_{day}')
            inicio = st.time_input('Desde', value=datetime.strptime('18:00' if day != 'Friday' else '17:00', '%H:%M').time(), key=f'from_{day}')
            fin = st.time_input('Hasta', value=datetime.strptime('21:30', '%H:%M').time(), key=f'to_{day}')
            disponibilidad[day] = (inicio.strftime('%H:%M'), fin.strftime('%H:%M')) if activo else None
    if st.button('Cerrar sesión'):
        st.session_state.authenticated = False
        st.rerun()

recomendaciones = []
for clase in clases:
    if clase['nombre'] not in puntuaciones:
        continue
    dia = datetime.strptime(clase['fecha'], '%Y-%m-%d').strftime('%A')
    horario = disponibilidad.get(dia)
    if horario and horario[0] <= clase['inicio'] and clase['fin'] <= horario[1]:
        recomendaciones.append({**clase, 'Puntos': puntuaciones[clase['nombre']]})

st.metric('Clases que encajan contigo', len(recomendaciones))


def color_puntos(valor):
    if valor >= 4:
        return 'background-color: #d4edda; color: #155724'
    if valor == 3:
        return 'background-color: #fff3cd; color: #856404'
    return 'background-color: #f8d7da; color: #721c24'


if not recomendaciones:
    st.info('No hay clases que coincidan con tus preferencias y horarios esta semana.')
else:
    for fecha in sorted({c['fecha'] for c in recomendaciones}):
        dia = datetime.strptime(fecha, '%Y-%m-%d')
        st.markdown(f'### 📅 {DAYS[dia.strftime("%A")]} {dia.strftime("%d/%m")}')
        grupo = sorted((c for c in recomendaciones if c['fecha'] == fecha), key=lambda c: (-c['Puntos'], c['inicio']))
        ids = [f"{c['fecha']}|{c['id']}" for c in grupo]
        df = pd.DataFrame({
            'Actividad': [c['nombre'] for c in grupo],
            'Horario': [f"{c['inicio']}–{c['fin']}" for c in grupo],
            'Sala': [c['sala'] for c in grupo],
            'Puntos': [c['Puntos'] for c in grupo],
            'La elijo': [bool(guardadas.get(cid, {}).get('selected', False)) for cid in ids],
        })
        firma = hashlib.sha1('|'.join(ids).encode()).hexdigest()[:12]
        editado = st.data_editor(
            df.style.map(color_puntos, subset=['Puntos']),
            hide_index=True, use_container_width=True,
            disabled=['Actividad', 'Horario', 'Sala', 'Puntos'],
            column_config={
                'Actividad': st.column_config.TextColumn('Actividad'),
                'Horario': st.column_config.TextColumn('Horario'),
                'Sala': st.column_config.TextColumn('Sala'),
                'Puntos': st.column_config.NumberColumn('Puntos', format='%d'),
                'La elijo': st.column_config.CheckboxColumn('La elijo', help='Marca la clase que planeas hacer'),
            },
            key=f'editor_{fecha}_{firma}',
        )
        for clase, cid, elegida in zip(grupo, ids, editado['La elijo'].tolist()):
            antes = bool(guardadas.get(cid, {}).get('selected', False))
            if bool(elegida) != antes:
                try:
                    guardar_decision(clase, bool(elegida))
                    guardadas[cid] = {**guardadas.get(cid, {}), 'class_id': cid, 'class_date': clase['fecha'], 'activity': clase['nombre'], 'start_time': clase['inicio'], 'end_time': clase['fin'], 'room': clase['sala'], 'selected': bool(elegida)}
                except Exception as exc:
                    st.error(f'No se pudo guardar la selección de {clase["nombre"]}: {exc}')

st.divider()
# Se incluyen clases elegidas aunque ya no cumplan los filtros actuales.
elegidas_semana = [r for r in guardadas.values() if r.get('selected')]
st.subheader(f'✅ Mis clases elegidas: {len(elegidas_semana)}')
if elegidas_semana:
    resumen = pd.DataFrame([{
        'Día': f"{DAYS[datetime.strptime(r['class_date'], '%Y-%m-%d').strftime('%A')]} {datetime.strptime(r['class_date'], '%Y-%m-%d').strftime('%d/%m')}",
        'Actividad': r['activity'],
        'Horario': f"{r['start_time']}–{r.get('end_time') or ''}",
        'Sala': r.get('room') or 'Sin especificar',
    } for r in sorted(elegidas_semana, key=lambda r: (r['class_date'], r['start_time'])) if r.get('class_date')])
    if not resumen.empty:
        st.dataframe(resumen, hide_index=True, use_container_width=True)
else:
    st.caption('Marca «La elijo» en las tablas para preparar tu semana.')

st.divider()
st.subheader('📝 Revisión de asistencia')
st.caption('Al terminar una semana, confirma a cuáles de tus clases elegidas asististe realmente.')
semanas_pasadas = list(range(1, 9))
semana_revision = st.selectbox(
    'Semana que quieres revisar', semanas_pasadas,
    format_func=lambda n: f'{(lunes_actual - timedelta(weeks=n)).strftime("%d/%m")} – {(lunes_actual - timedelta(weeks=n) + timedelta(days=6)).strftime("%d/%m/%Y")}',
)
lunes_revision = lunes_actual - timedelta(weeks=semana_revision)
try:
    historial = registros_semana(lunes_revision)
except Exception as exc:
    st.error(f'No se pudo cargar la revisión semanal: {exc}')
    st.stop()

pendientes = sorted(
    (r for r in historial.values() if r.get('selected')),
    key=lambda r: (r['class_date'], r['start_time']),
)
if not pendientes:
    st.info('No tienes clases elegidas registradas para esa semana.')
else:
    opciones = ['Pendiente', 'Sí, asistí', 'No asistí']
    df_revision = pd.DataFrame([{
        'Actividad': r['activity'],
        'Día': r['class_date'],
        'Horario': r['start_time'],
        'Asistencia': 'Pendiente' if r.get('attended') is None else ('Sí, asistí' if r['attended'] else 'No asistí'),
    } for r in pendientes])
    editado_revision = st.data_editor(
        df_revision, hide_index=True, use_container_width=True,
        disabled=['Actividad', 'Día', 'Horario'],
        column_config={'Asistencia': st.column_config.SelectboxColumn('¿Has ido?', options=opciones, required=True)},
        key=f'revision_{lunes_revision}',
    )
    cambios = 0
    for r, nuevo in zip(pendientes, editado_revision['Asistencia'].tolist()):
        antes = 'Pendiente' if r.get('attended') is None else ('Sí, asistí' if r['attended'] else 'No asistí')
        if nuevo != antes:
            valor = None if nuevo == 'Pendiente' else nuevo == 'Sí, asistí'
            try:
                guardar_asistencia(r['class_id'], valor)
                cambios += 1
            except Exception as exc:
                st.error(f'No se pudo guardar la asistencia a {r["activity"]}: {exc}')
    if cambios:
        st.success('Asistencia guardada en Supabase.')

st.caption('Tus elecciones y asistencias se guardan en Supabase. Seleccionar una clase aquí no equivale a reservarla en BeOne.')
