import streamlit as st
import pandas as pd
import math
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(page_title="Ruteo Sabor Sabanero", page_icon="🚚", layout="wide")

# ==========================================
# INICIALIZACIÓN DE DATOS (Por defecto los de tu script)
# ==========================================
if 'datos_ubicaciones' not in st.session_state:
    st.session_state.datos_ubicaciones = pd.DataFrame({
        'Tipo': ['CEDI', 'Cliente', 'Cliente', 'Cliente', 'Cliente', 'Cliente'],
        'Nombre': ["CEDI Tocancipá", "Chía", "Cajicá", "Zipaquirá", "Sopó", "Briceño"],
        'Latitud': [4.964, 4.863, 4.918, 4.996, 4.908, 4.945],
        'Longitud': [-73.912, -74.053, -74.029, -74.003, -73.938, -73.921],
        'Demanda (kg)': [0, 1100, 750, 1400, 900, 500]
    })

# ==========================================
# FUNCIONES DE RUTEO (Tu código adaptado)
# ==========================================
def calcular_distancia_euclidiana(coord1, coord2):
    lat1, lon1 = coord1[0], coord1[1]
    lat2, lon2 = coord2[0], coord2[1]
    distancia_grados = math.sqrt((lat2 - lat1)**2 + (lon2 - lon1)**2)
    return int(distancia_grados * 111000)

def extraer_rutas(data, manager, routing, solution):
    rutas = []
    for id_vehiculo in range(data['num_vehiculos']):
        ruta_vehiculo = []
        index = routing.Start(id_vehiculo)
        distancia_acumulada = 0
        
        while not routing.IsEnd(index):
            nodo_actual = manager.IndexToNode(index)
            indice_anterior = index
            index = solution.Value(routing.NextVar(index))
            distancia_tramo = routing.GetArcCostForVehicle(indice_anterior, index, id_vehiculo)
            distancia_acumulada += distancia_tramo
            
            ruta_vehiculo.append({
                'nodo': nodo_actual,
                'nombre': data['nombres_nodos'][nodo_actual],
                'coordenadas': data['coordenadas'][nodo_actual],
                'demanda': data['demandas'][nodo_actual]
            })
            
        nodo_final = manager.IndexToNode(index)
        ruta_vehiculo.append({
            'nodo': nodo_final,
            'nombre': data['nombres_nodos'][nodo_final],
            'coordenadas': data['coordenadas'][nodo_final],
            'demanda': data['demandas'][nodo_final]
        })
        
        rutas.append({
            'id_vehiculo': id_vehiculo + 1,
            'trayecto': ruta_vehiculo,
            'distancia_total_m': distancia_acumulada,
            'capacidad_maxima': data['capacidades_vehiculos'][id_vehiculo]
        })
    return rutas

def resolver_ruteo(df_ubicaciones, num_vehiculos, cap_vehiculo):
    datos = {}
    datos['coordenadas'] = df_ubicaciones[['Latitud', 'Longitud']].values.tolist()
    datos['nombres_nodos'] = df_ubicaciones['Nombre'].tolist()
    datos['demandas'] = df_ubicaciones['Demanda (kg)'].tolist()
    
    num_puntos = len(datos['coordenadas'])
    matriz_distancias = []
    for i in range(num_puntos):
        fila = []
        for j in range(num_puntos):
            fila.append(calcular_distancia_euclidiana(datos['coordenadas'][i], datos['coordenadas'][j]))
        matriz_distancias.append(fila)
        
    datos['matriz_distancias'] = matriz_distancias
    datos['capacidades_vehiculos'] = [cap_vehiculo] * num_vehiculos
    datos['num_vehiculos'] = num_vehiculos
    datos['deposito'] = 0 # Siempre asumimos que el índice 0 es el CEDI
    
    manager = pywrapcp.RoutingIndexManager(len(datos['matriz_distancias']), datos['num_vehiculos'], datos['deposito'])
    routing = pywrapcp.RoutingModel(manager)

    def callback_distancia(desde_index, hacia_index):
        desde_nodo = manager.IndexToNode(desde_index)
        hacia_nodo = manager.IndexToNode(hacia_index)
        return datos['matriz_distancias'][desde_nodo][hacia_nodo]

    transit_callback_index = routing.RegisterTransitCallback(callback_distancia)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def callback_demanda(desde_index):
        desde_nodo = manager.IndexToNode(desde_index)
        return datos['demandas'][desde_nodo]

    demand_callback_index = routing.RegisterUnaryTransitCallback(callback_demanda)

    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0, 
        datos['capacidades_vehiculos'], 
        True, 
        'Capacidad'
    )

    parametros_busqueda = pywrapcp.DefaultRoutingSearchParameters()
    parametros_busqueda.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    parametros_busqueda.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parametros_busqueda.time_limit.seconds = 2

    solucion = routing.SolveWithParameters(parametros_busqueda)

    if solucion:
        return extraer_rutas(datos, manager, routing, solucion)
    else:
        return None

# ==========================================
# INTERFAZ DE USUARIO (STREAMLIT)
# ==========================================
st.title("🚚 Optimización de Rutas - Sabor Sabanero S.A.S.")
st.markdown("Bienvenido al sistema de ruteo. Añade las ubicaciones buscando por dirección o edita la tabla directamente.")

# BARRA LATERAL: Configuración de Flota
st.sidebar.header("⚙️ Configuración de Flota")
num_vehiculos = st.sidebar.number_input("Número de vehículos", min_value=1, max_value=20, value=3)
cap_vehiculo = st.sidebar.number_input("Capacidad por vehículo (kg)", min_value=100, max_value=10000, value=2200)

# SECCIÓN 1: Buscador de Coordenadas
st.header("📍 Buscar y Agregar Ubicaciones")
col1, col2, col3, col4 = st.columns([2, 3, 1, 1])

with col1:
    tipo_lugar = st.selectbox("Tipo", ["Cliente", "CEDI"])
with col2:
    direccion_buscar = st.text_input("Buscar dirección (Ej: Parque Central, Zipaquirá, Colombia)")
with col3:
    demanda_input = st.number_input("Demanda (kg)", min_value=0, value=500 if tipo_lugar=="Cliente" else 0)
with col4:
    st.markdown("<br>", unsafe_allow_html=True)
    btn_buscar = st.button("Buscar y Agregar", use_container_width=True)

if btn_buscar and direccion_buscar:
    geolocator = Nominatim(user_agent="sabor_sabanero_app_seb")
    location = geolocator.geocode(direccion_buscar)
    if location:
        nueva_fila = pd.DataFrame([{
            'Tipo': tipo_lugar,
            'Nombre': direccion_buscar.split(",")[0],
            'Latitud': location.latitude,
            'Longitud': location.longitude,
            'Demanda (kg)': demanda_input
        }])
        if tipo_lugar == "CEDI":
            # Si es CEDI lo ponemos al principio (índice 0)
            st.session_state.datos_ubicaciones = pd.concat([nueva_fila, st.session_state.datos_ubicaciones], ignore_index=True)
        else:
            st.session_state.datos_ubicaciones = pd.concat([st.session_state.datos_ubicaciones, nueva_fila], ignore_index=True)
        st.success(f"✅ Agregado: {location.address}")
    else:
        st.error("❌ No se encontró la dirección. Intenta ser más específico (agrega ciudad y país).")

# SECCIÓN 2: Tabla de Datos (Editable)
st.subheader("📋 Puntos de la Operación (Editable)")
st.info("Nota: La primera fila SIEMPRE debe ser tu CEDI (Punto de partida). Puedes editar los valores directamente en la tabla.")
df_editado = st.data_editor(st.session_state.datos_ubicaciones, num_rows="dynamic", use_container_width=True)
st.session_state.datos_ubicaciones = df_editado

# SECCIÓN 3: Botón de Ejecución
st.markdown("---")
if st.button("🚀 CALCULAR RUTAS ÓPTIMAS", type="primary", use_container_width=True):
    if len(df_editado) < 2:
        st.error("Necesitas al menos 1 CEDI y 1 Cliente para calcular la ruta.")
    else:
        with st.spinner('Procesando algoritmo de optimización...'):
            rutas = resolver_ruteo(df_editado, num_vehiculos, cap_vehiculo)
            
            if rutas:
                st.success("✅ ¡Rutas calculadas con éxito!")
                
                tab_resumen, tab_mapa = st.tabs(["📊 Resumen de Operación", "🗺️ Mapa Interactivo"])
                
                with tab_resumen:
                    gran_distancia = 0
                    gran_carga = 0
                    
                    for r in rutas:
                        dist_km = r['distancia_total_m'] / 1000
                        carga_total = sum([p['demanda'] for p in r['trayecto']])
                        gran_distancia += r['distancia_total_m']
                        gran_carga += carga_total
                        
                        if len(r['trayecto']) <= 2 and carga_total == 0:
                            continue # Vehículo no utilizado
                            
                        with st.expander(f"🟢 Vehículo {r['id_vehiculo']} | Carga: {carga_total}kg | Distancia: {dist_km:.2f}km", expanded=True):
                            carga_acumulada = 0
                            for i, punto in enumerate(r['trayecto']):
                                carga_acumulada += punto['demanda']
                                icon = "🏢" if i == 0 or i == len(r['trayecto'])-1 else "📍"
                                st.write(f"{icon} **{i+1}. {punto['nombre']}** | Entregado: {punto['demanda']}kg | Acumulado: {carga_acumulada}kg")
                                
                    st.metric("Carga Total Despachada", f"{gran_carga} kg")
                    st.metric("Distancia Total Recorrida", f"{gran_distancia / 1000:.2f} km")
                
                with tab_mapa:
                    # Crear mapa interactivo centrado en el CEDI
                    lat_cedi = df_editado.iloc[0]['Latitud']
                    lon_cedi = df_editado.iloc[0]['Longitud']
                    m = folium.Map(location=[lat_cedi, lon_cedi], zoom_start=11)
                    
                    colores = ['blue', 'orange', 'green', 'red', 'purple', 'darkblue', 'cadetblue', 'pink', 'lightgreen']
                    
                    # Dibujar Rutas
                    for r in rutas:
                        carga_total = sum([p['demanda'] for p in r['trayecto']])
                        if carga_total > 0:
                            color = colores[(r['id_vehiculo'] - 1) % len(colores)]
                            coordenadas_ruta = [(p['coordenadas'][0], p['coordenadas'][1]) for p in r['trayecto']]
                            folium.PolyLine(coordenadas_ruta, color=color, weight=4, opacity=0.8, tooltip=f"Vehículo {r['id_vehiculo']}").add_to(m)
                    
                    # Dibujar Marcadores
                    for i, row in df_editado.iterrows():
                        if i == 0:
                            folium.Marker([row['Latitud'], row['Longitud']], tooltip=f"CEDI: {row['Nombre']}", icon=folium.Icon(color="black", icon="home")).add_to(m)
                        else:
                            folium.Marker([row['Latitud'], row['Longitud']], tooltip=f"Cliente: {row['Nombre']} ({row['Demanda (kg)']}kg)").add_to(m)
                    
                    st_folium(m, width=900, height=500)
            else:
                st.error("❌ No se encontró una solución. Intenta agregar más vehículos o aumentar su capacidad.")
