1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title='BeOne Gym Assistant', page_icon='🏋️', layout='wide')
st.title('🏋️ BeOne Gym Assistant')
st.caption('Tus clases recomendadas, de lunes a domingo')

DAYS = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
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
                # Si falta el ID, construimos uno a partir de los datos de la sesión.
                if identificador is None:
                    identificador = f"{fecha}|{clase.get('timeStart')}|{(clase.get('activity') or {}).get('name')}|{(clase.get('room') or {}).get('room')}"
                if identificador in vistos:
                    continue
                vistos.add(identificador)
                actividad = clase.get('activity') or {}
                sala = (clase.get('room') or {}).get('room') or 'Sin especificar'
                nombre = (actividad.get('name') or '').strip().upper()
                if not nombre or not clase.get('timeStart') or not clase.get('timeEnd'):
                    continue
                clases.append({
                    'id': str(identificador),
                    'fecha': fecha,
                    'nombre': nombre,
                    'sala': sala,
                    'inicio': clase['timeStart'][:5],
                    'fin': clase['timeEnd'][:5],
                })
    return clases

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
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f'No se pudieron consultar los horarios de BeOne: {exc}')
    st.stop()

actividades_disponibles = sorted({c['nombre'] for c in clases if c['nombre'] not in EXCLUIDAS})
seleccion_inicial = [a for a in PUNTOS_INICIALES if a in actividades_disponibles]

with st.sidebar:
    st.header('Mis preferencias')
    favoritas = st.multiselect(
        'Actividades que quiero hacer',
        options=actividades_disponibles,
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
