import os
import pandas as pd
import shutil
import sqlite3

# Directorios
input_dir = 'csv'
imported_dir = 'csv/imported'

# Columnas obligatorias y opcionales
required_columns = ['Iceberg', 'Length (NM)', 'Width (NM)', 'Latitude', 'Longitude', 'Last Update']
optional_columns = ['Area (sqMI)', 'Area (sqNM)', 'Area (sqKM)']

# Conectar a la base de datos SQLite (si no existe, se crea)
db_path = 'iceberg_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Crear la tabla si no existe
cursor.execute("""
CREATE TABLE IF NOT EXISTS icebergs (
    Iceberg TEXT,
    Length REAL,
    Width REAL,
    Latitude REAL,
    Longitude REAL,
    LastUpdate TEXT,
    Area_sqMI REAL,
    Area_sqNM REAL,
    Area_sqKM REAL
)
""")
conn.commit()

def load_csv(file_path):
    try:
        # Leer el archivo CSV, omitiendo líneas con errores
        df = pd.read_csv(file_path, on_bad_lines='skip')
    except Exception as e:
        print(f"Error al leer el archivo {os.path.basename(file_path)}: {e}")
        return None, []
    
    # Filtrar las columnas necesarias
    columns_to_import = [col for col in required_columns if col in df.columns]
    columns_to_import += [col for col in optional_columns if col in df.columns]
    
    # Crear un DataFrame con solo las columnas necesarias y opcionales
    df_filtered = df[columns_to_import]
    
    # Verificar qué columnas faltan
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    # Si faltan columnas obligatorias, informar pero no detener el proceso
    if missing_columns:
        print(f"Archivo {os.path.basename(file_path)} omiso: Columnas obligatorias faltantes: {', '.join(missing_columns)}")
    else:
        print(f"Archivo {os.path.basename(file_path)} cargado correctamente.")
    
    # Devolver el dataframe filtrado y las columnas faltantes
    return df_filtered, missing_columns


# Función para mover el archivo
def move_file(file_path):
    shutil.move(file_path, os.path.join(imported_dir, os.path.basename(file_path)))
    print(f"Archivo {os.path.basename(file_path)} movido a {imported_dir}")

# Función para insertar los datos en la base de datos SQLite
def insert_data_to_db(df):
    if df is not None:  # Verificar que df no sea None antes de procesarlo
        for _, row in df.iterrows():
            cursor.execute("""
            INSERT INTO icebergs (Iceberg, Length, Width, Latitude, Longitude, LastUpdate, Area_sqMI, Area_sqNM, Area_sqKM)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['Iceberg'],
                row['Length (NM)'],
                row['Width (NM)'],
                row['Latitude'],
                row['Longitude'],
                row['Last Update'],
                row.get('Area (sqMI)', None),  # Usar None si no está presente
                row.get('Area (sqNM)', None),
                row.get('Area (sqKM)', None)
            ))
        conn.commit()
    else:
        print("No se cargaron datos para insertar en la base de datos.")

# Función principal para procesar los archivos CSV
def process_files():
    # Verificar si el directorio de archivos importados existe
    if not os.path.exists(imported_dir):
        os.makedirs(imported_dir)

    # Procesar todos los archivos CSV en el directorio
    for filename in os.listdir(input_dir):
        if filename.endswith('.csv'):
            file_path = os.path.join(input_dir, filename)
            
            # Cargar el archivo CSV y obtener las columnas faltantes
            df_filtered, missing_columns = load_csv(file_path)
            
            # Si faltan columnas obligatorias, se omite el archivo
            if missing_columns:
                move_file(file_path)  # Mover el archivo a la carpeta "imported"
                continue
            
            # Insertar los datos en la base de datos SQLite
            insert_data_to_db(df_filtered)
            
            # Mover el archivo procesado a la carpeta "imported"
            move_file(file_path)

# Llamada a la función principal para procesar los archivos
if __name__ == "__main__":
    process_files()

    # Cerrar la conexión a la base de datos SQLite
    conn.close()
