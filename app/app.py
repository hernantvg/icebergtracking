from flask import Flask, render_template, request
import pandas as pd
import requests
import io
import folium

app = Flask(__name__)

def fetch_iceberg_data():
    url = "https://usicecenter.gov/File/DownloadCurrent?pId=134"
    response = requests.get(url)
    if response.status_code == 200:
        csv_data = io.StringIO(response.text)
        df = pd.read_csv(csv_data)
        return df
    else:
        return pd.DataFrame()

def create_map(data):
    iceberg_map = folium.Map(location=[-60, -40], zoom_start=3)
    for _, row in data.iterrows():
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=f"{row['Iceberg']} - {row['Last Update']}\nArea (sqKM): {row['Area (sqKM)']}"
        ).add_to(iceberg_map)
    return iceberg_map._repr_html_()

@app.route('/')
def index():
    data = fetch_iceberg_data()
    if data.empty:
        message = "No data available. Please try again later."
        return render_template('index.html', message=message)

    iceberg_map = create_map(data)
    return render_template('index.html', icebergs=data.to_dict('records'), iceberg_map=iceberg_map)

@app.route('/filter', methods=['POST'])
def filter_data():
    data = fetch_iceberg_data()
    if data.empty:
        message = "No data available. Please try again later."
        return render_template('index.html', message=message)

    min_length = request.form.get('min_length', type=float)
    max_length = request.form.get('max_length', type=float)
    filtered_data = data[(data['Length (NM)'] >= min_length) & (data['Length (NM)'] <= max_length)]
    iceberg_map = create_map(filtered_data)
    return render_template('index.html', icebergs=filtered_data.to_dict('records'), iceberg_map=iceberg_map)

if __name__ == '__main__':
    app.run(debug=True)
