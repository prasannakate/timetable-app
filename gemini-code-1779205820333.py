import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("design_college.db")
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program TEXT, division TEXT, semester_type TEXT
        );
        CREATE TABLE IF NOT EXISTS faculties (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT
        );
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT
        );
        CREATE TABLE IF NOT EXISTS faculty_subject_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER, faculty_id INTEGER, subject_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS holiday_master (
            date TEXT PRIMARY KEY, description TEXT
        );
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, class_id INTEGER, morning_subject_id INTEGER, afternoon_subject_id INTEGER
        );
    ''')
    conn.commit()
    return conn

conn = init_db()
cursor = conn.cursor()

# --- HELPER FUNCTIONS ---
def get_classes():
    return pd.read_sql_query("SELECT id, program || ' - Div ' || division || ' (' || semester_type || ' Sem)' as class_name FROM classes", conn)

def get_faculties():
    return pd.read_sql_query("SELECT * FROM faculties", conn)

def get_subjects():
    return pd.read_sql_query("SELECT * FROM subjects", conn)

# --- UI SETUP ---
st.set_page_config(page_title="Timetable Manager", layout="wide")
st.title("📅 College Timetable Generator")

# Sidebar Navigation
menu = st.sidebar.radio("Navigation", ["1. Add Master Data", "2. Map Faculties & Subjects", "3. Generate Timetable", "4. View Timetable"])

# --- 1. ADD MASTER DATA ---
if menu == "1. Add Master Data":
    st.header("Master Data Entry")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Add Class")
        with st.form("class_form", clear_on_submit=True):
            program = st.selectbox("Program", ["B.Des.", "M.Des."])
            division = st.text_input("Division (e.g., A, B)")
            semester = st.selectbox("Semester", ["Odd", "Even"])
            if st.form_submit_button("Save Class"):
                cursor.execute("INSERT INTO classes (program, division, semester_type) VALUES (?, ?, ?)", (program, division, semester))
                conn.commit()
                st.success("Class added!")

    with col2:
        st.subheader("Add Faculty / Subject")
        with st.form("fac_sub_form", clear_on_submit=True):
            entry_type = st.radio("Type", ["Faculty", "Subject"])
            name = st.text_input("Name")
            if st.form_submit_button("Save Entry"):
                table = "faculties" if entry_type == "Faculty" else "subjects"
                cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
                conn.commit()
                st.success(f"{entry_type} added!")

    with col3:
        st.subheader("Add Holiday")
        with st.form("holiday_form", clear_on_submit=True):
            h_date = st.date_input("Holiday Date")
            h_desc = st.text_input("Description")
            if st.form_submit_button("Save Holiday"):
                try:
                    cursor.execute("INSERT INTO holiday_master (date, description) VALUES (?, ?)", (str(h_date), h_desc))
                    conn.commit()
                    st.success("Holiday added!")
                except sqlite3.IntegrityError:
                    st.error("Holiday already exists for this date.")

# --- 2. MAP FACULTIES TO SUBJECTS ---
elif menu == "2. Map Faculties & Subjects":
    st.header("Map Subjects and Faculties to a Class")
    classes_df = get_classes()
    faculties_df = get_faculties()
    subjects_df = get_subjects()

    if classes_df.empty or faculties_df.empty or subjects_df.empty:
        st.warning("Please add at least one Class, Faculty, and Subject in Master Data first.")
    else:
        with st.form("mapping_form"):
            selected_class = st.selectbox("Select Class", classes_df['class_name'])
            class_id = classes_df.loc[classes_df['class_name'] == selected_class, 'id'].values[0]
            
            selected_subject = st.selectbox("Select Subject", subjects_df['name'])
            sub_id = subjects_df.loc[subjects_df['name'] == selected_subject, 'id'].values[0]
            
            selected_faculty = st.selectbox("Select Faculty", faculties_df['name'])
            fac_id = faculties_df.loc[faculties_df['name'] == selected_faculty, 'id'].values[0]
            
            if st.form_submit_button("Map to Class"):
                cursor.execute("INSERT INTO faculty_subject_mapping (class_id, faculty_id, subject_id) VALUES (?, ?, ?)", (int(class_id), int(fac_id), int(sub_id)))
                conn.commit()
                st.success(f"Mapped {selected_subject} ({selected_faculty}) to {selected_class}")

# --- 3. GENERATE TIMETABLE ---
elif menu == "3. Generate Timetable":
    st.header("Generate Weekly Timetable")
    classes_df = get_classes()
    
    if classes_df.empty:
        st.warning("No classes available.")
    else:
        selected_class = st.selectbox("Select Class to Schedule", classes_df['class_name'])
        class_id = classes_df.loc[classes_df['class_name'] == selected_class, 'id'].values[0]
        start_date = st.date_input("Start Date (Ideally a Monday)")
        
        if st.button("Generate Timetable"):
            # Fetch mapped subjects
            cursor.execute("SELECT subject_id FROM faculty_subject_mapping WHERE class_id = ?", (int(class_id),))
            subjects = [row[0] for row in cursor.fetchall()]
            
            if not subjects:
                st.error("No subjects mapped to this class! Go to Step 2.")
            else:
                current_date = start_date
                days_scheduled = 0
                sub_idx = 0
                
                while days_scheduled < 5: # Schedule for 5 working days
                    date_str = current_date.strftime("%Y-%m-%d")
                    
                    if current_date.weekday() >= 5: # Skip weekends
                        current_date += timedelta(days=1)
                        continue
                        
                    cursor.execute("SELECT * FROM holiday_master WHERE date = ?", (date_str,))
                    if cursor.fetchone(): # Skip holidays
                        current_date += timedelta(days=1)
                        continue
                        
                    morning_sub = subjects[sub_idx % len(subjects)]
                    sub_idx += 1
                    afternoon_sub = subjects[sub_idx % len(subjects)]
                    sub_idx += 1
                    
                    cursor.execute('''INSERT INTO timetable (date, class_id, morning_subject_id, afternoon_subject_id)
                                      VALUES (?, ?, ?, ?)''', (date_str, int(class_id), morning_sub, afternoon_sub))
                    days_scheduled += 1
                    current_date += timedelta(days=1)
                
                conn.commit()
                st.success("Successfully generated 5 working days of classes!")

# --- 4. VIEW TIMETABLE ---
elif menu == "4. View Timetable":
    st.header("View Timetable")
    classes_df = get_classes()
    
    if not classes_df.empty:
        selected_class = st.selectbox("Filter by Class", classes_df['class_name'])
        class_id = classes_df.loc[classes_df['class_name'] == selected_class, 'id'].values[0]
        
        query = '''
            SELECT t.date as "Date", 
                   sm.name as "09:30 AM - 12:30 PM", 
                   sa.name as "01:30 PM - 04:30 PM"
            FROM timetable t
            LEFT JOIN subjects sm ON t.morning_subject_id = sm.id
            LEFT JOIN subjects sa ON t.afternoon_subject_id = sa.id
            WHERE t.class_id = ?
            ORDER BY t.date ASC
        '''
        df = pd.read_sql_query(query, conn, params=(int(class_id),))
        
        if df.empty:
            st.info("No timetable generated for this class yet.")
        else:
            st.table(df)
