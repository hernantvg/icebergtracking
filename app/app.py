from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import os
import folium
from folium import PolyLine

app = Flask(__name__)

def fetch_latest_csv():
    folder_path = "csv"
    csv_files = [file for file in os.listdir(folder_path) if file.endswith(".csv")]
    if not csv_files:
        return None
    latest_file = max(csv_files, key=lambda x: os.path.getctime(os.path.join(folder_path, x)))
    return os.path.join(folder_path, latest_file)

def fetch_iceberg_data_from_folder():
    folder_path = "csv/archive"
    all_data = pd.DataFrame()

    # Buscar archivos en el folder "csv/archive"
    for file in os.listdir(folder_path):
        if file.endswith(".csv"):
            file_path = os.path.join(folder_path, file)
            try:
                df = pd.read_csv(file_path, on_bad_lines='skip')
                all_data = pd.concat([all_data, df], ignore_index=True)
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    # Añadir el archivo más reciente de "csv"
    latest_file = fetch_latest_csv()
    if latest_file:
        try:
            latest_data = pd.read_csv(latest_file, on_bad_lines='skip')
            all_data = pd.concat([all_data, latest_data], ignore_index=True)
        except Exception as e:
            print(f"Error reading {latest_file}: {e}")
            
    return all_data

def fetch_latest_positions():
    latest_file = fetch_latest_csv()
    if not latest_file:
        return pd.DataFrame()

    try:
        data = pd.read_csv(latest_file, on_bad_lines='skip')
        if 'Last Update' in data.columns:
            # Intentar convertir 'Last Update' a formato datetime
            data['Last Update'] = pd.to_datetime(data['Last Update'], errors='coerce')
            # Eliminar filas con fechas inválidas
            data = data.dropna(subset=['Last Update'])
        else:
            print(f"'Last Update' column not found in {latest_file}.")
            return pd.DataFrame()

        # Ordenar por Iceberg y Last Update (de más reciente a más antiguo)
        latest_positions = data.sort_values(by=['Iceberg', 'Last Update'], ascending=[True, False])
        # Eliminar duplicados para cada iceberg
        latest_positions = latest_positions.drop_duplicates(subset=['Iceberg'])
        return latest_positions
    except Exception as e:
        print(f"Error reading latest CSV {latest_file}: {e}")
        return pd.DataFrame()

def create_map(data):
    iceberg_map = folium.Map(location=[-60, -40], zoom_start=3)

    for iceberg, group in data.groupby('Iceberg'):
        coordinates = group[['Latitude', 'Longitude']].dropna().values.tolist()
        # Agrega una línea entre puntos consecutivos
        if len(coordinates) > 1:
            PolyLine(locations=coordinates, color="blue", weight=2.5, opacity=1).add_to(iceberg_map)
        # Marcadores individuales para cada punto
        for _, row in group.iterrows():
            area = row.get('Area (sqKM)', "N/A")
            folium.Marker(
                location=[row['Latitude'], row['Longitude']],
                popup=f"{row['Iceberg']} - {row['Last Update']}\nArea (sqKM): {area}"
            ).add_to(iceberg_map)

    return iceberg_map._repr_html_()

def create_current_positions_map(latest_positions):
    iceberg_map = folium.Map(location=[-60, -40], zoom_start=3)

    for _, row in latest_positions.iterrows():
        area = row.get('Area (sqKM)', "N/A")
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=f"{row['Iceberg']} - Last Update: {row['Last Update']}\nArea (sqKM): {area}",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(iceberg_map)

    return iceberg_map._repr_html_()

@app.route('/')
def index():
    data = fetch_iceberg_data_from_folder()
    if data.empty:
        message = "No data available. Please add CSV files to the 'csv' folder."
        return render_template('index.html', message=message, iceberg_map=None, icebergs=[], iceberg_info=None, current_positions_map=None)

    icebergs = data['Iceberg'].dropna().unique().tolist()
    latest_positions = fetch_latest_positions()
    current_positions_map = create_current_positions_map(latest_positions) if not latest_positions.empty else None

    return render_template('index.html', message=None, iceberg_map=None, icebergs=icebergs, iceberg_info=None, current_positions_map=current_positions_map)

# Nueva ruta que redirige a /select
@app.route('/tracking')
def tracking():
    return redirect(url_for('select_iceberg'))

@app.route('/select', methods=['GET', 'POST'])
def select_iceberg():
    data = fetch_iceberg_data_from_folder()
    if data.empty:
        message = "No data available. Please add CSV files to the 'csv' folder."
        return render_template('tracking.html', message=message, iceberg_map=None, icebergs=[], iceberg_info=None, current_positions_map=None)

    # Si el método es POST (cuando se envía el formulario)
    if request.method == 'POST':
        selected_iceberg = request.form.get('iceberg')
        filtered_data = data[data['Iceberg'] == selected_iceberg]

        if filtered_data.empty:
            message = f"No data found for iceberg {selected_iceberg}."
            return render_template('tracking.html', message=message, iceberg_map=None, icebergs=data['Iceberg'].unique().tolist(), iceberg_info=None, current_positions_map=None)

        iceberg_map = create_map(filtered_data)

        iceberg_info = {
            'name': selected_iceberg,
            'last_update': filtered_data['Last Update'].iloc[0],
            'area': filtered_data.get('Area (sqKM)', pd.Series(["N/A"])).iloc[0],
            'location': f"Latitude: {filtered_data['Latitude'].iloc[0]}, Longitude: {filtered_data['Longitude'].iloc[0]}"
        }

        latest_positions = fetch_latest_positions()
        current_positions_map = create_current_positions_map(latest_positions) if not latest_positions.empty else None

        return render_template('tracking.html', message=None, iceberg_map=iceberg_map, icebergs=data['Iceberg'].unique().tolist(), iceberg_info=iceberg_info, current_positions_map=current_positions_map)

    # Si el método es GET (cuando se carga la página inicialmente)
    else:
        return render_template('tracking.html', message=None, iceberg_map=None, icebergs=data['Iceberg'].unique().tolist(), iceberg_info=None, current_positions_map=None)


if __name__ == '__main__':
    app.run(debug=True)