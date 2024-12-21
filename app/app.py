from flask import Flask, render_template, request
import pandas as pd
import sqlite3
import os
import folium
from folium import PolyLine

app = Flask(__name__)

DB_PATH = 'iceberg_data.db'

# Función para obtener la conexión a la base de datos
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Esto permite acceder a los resultados como diccionarios
    return conn

# Función para obtener los datos de los icebergs desde la base de datos
def fetch_iceberg_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM icebergs')
    data = cursor.fetchall()  # Devuelve una lista de diccionarios
    conn.close()
    
    # Convertir la lista de diccionarios a un DataFrame
    df = pd.DataFrame(data)
    
    # Limpiar los nombres de las columnas eliminando espacios solo si son cadenas
    df.columns = [col.strip() if isinstance(col, str) else col for col in df.columns]
    
    return df

# Función para crear el mapa con Folium
def create_map(data):
    iceberg_map = folium.Map(location=[-60, -40], zoom_start=3)
    
    # Asegúrate de que 'data' sea un DataFrame
    if isinstance(data, pd.DataFrame):
        for iceberg, group in data.groupby('Iceberg'):
            coordinates = group[['Latitude', 'Longitude']].dropna().values.tolist()
            # Agrega una línea entre puntos consecutivos
            if len(coordinates) > 1:
                PolyLine(locations=coordinates, color="blue", weight=2.5, opacity=1).add_to(iceberg_map)
            # Marcadores individuales para cada punto
            for _, row in group.iterrows():
                folium.Marker(
                    location=[row['Latitude'], row['Longitude']],
                    popup=f"{row['Iceberg']} - {row['Last Update']}\nArea (sqKM): {row['Area (sqKM)']}"
                ).add_to(iceberg_map)
    else:
        print("El dato pasado no es un DataFrame válido.")
    
    return iceberg_map._repr_html_()

# Ruta principal
@app.route('/')
def index():
    data = fetch_iceberg_data()
    if data.empty:
        message = "No data available. Please load data into the database."
        return render_template('index.html', message=message, iceberg_map=None, icebergs=[], iceberg_info=None)

    icebergs = data['Iceberg'].dropna().unique().tolist()
    return render_template('index.html', message=None, iceberg_map=None, icebergs=icebergs, iceberg_info=None)

# Ruta para seleccionar un iceberg y mostrar su información en el mapa
@app.route('/select', methods=['POST'])
def select_iceberg():
    data = fetch_iceberg_data()
    if data.empty:
        message = "No data available. Please load data into the database."
        return render_template('index.html', message=message, iceberg_map=None, icebergs=[], iceberg_info=None)

    selected_iceberg = request.form.get('iceberg')
    filtered_data = data[data['Iceberg'] == selected_iceberg]

    if filtered_data.empty:
        message = f"No data found for iceberg {selected_iceberg}."
        return render_template('index.html', message=message, iceberg_map=None, icebergs=data['Iceberg'].unique().tolist(), iceberg_info=None)

    iceberg_map = create_map(filtered_data)

    iceberg_info = {
        'name': selected_iceberg,
        'last_update': filtered_data['Last Update'].iloc[0],
        'area': filtered_data['Area (sqKM)'].iloc[0],
        'location': f"Latitude: {filtered_data['Latitude'].iloc[0]}, Longitude: {filtered_data['Longitude'].iloc[0]}"
    }

    return render_template('index.html', message=None, iceberg_map=iceberg_map, icebergs=data['Iceberg'].unique().tolist(), iceberg_info=iceberg_info)

if __name__ == '__main__':
    app.run(debug=True)
