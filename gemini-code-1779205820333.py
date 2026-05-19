import streamlit as st
import sqlite3
import pandas as pd
import io
from datetime import datetime, timedelta

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("design_college.db")
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program TEXT, branch TEXT, division TEXT, semester_type TEXT
        );
        CREATE TABLE IF NOT EXISTS faculties (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, faculty_type TEXT
        );
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT
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
    # Includes Program, Branch, Division, and Semester in the dropdown name
    query = "SELECT id, program || ' (' || branch || ') - Div ' || division || ' [' || semester_type || ' Sem]' as class_name FROM classes"
    return pd.read_sql_query(query, conn)

def get_faculties():
    return pd.read_sql_query("SELECT * FROM faculties", conn)

def get_subjects():
    return pd.read_sql_query("SELECT * FROM subjects", conn)

# --- UI SETUP ---
st.set_page_config(page_title="Timetable Manager", layout="wide")
st.title("📅 College Timetable Generator (Pro)")

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
            branch = st.selectbox("Branch", ["Product Design", "UX Design", "Graphic Design", "Interior Design", "Fashion Design"])
            division = st.text_input("Division (e.g., A, B)")
            semester = st.selectbox("Semester", ["Odd", "Even"])
            
            if st.form_submit_button("Save Class"):
                if division:
                    cursor.execute("INSERT INTO classes (program, branch, division, semester_type) VALUES (?, ?, ?, ?)", 
                                   (program, branch, division, semester))
                    conn.commit()
                    st.success("Class added!")
                else:
                    st.error("Division cannot be empty.")

    with col2:
        st.subheader("Add Faculty / Subject")
        with st.form("fac_sub_form", clear_on_submit=True):
            entry_type = st.radio("Type", ["Faculty", "Subject"])
            name = st.text_input("Name")
            
            # Only show Faculty Type if Faculty is selected
            faculty_type = None
            if entry_type == "Faculty":
                faculty_type = st.radio("Faculty Type", ["Full-Time", "Visiting"])
                
            if st.form_submit_button("Save Entry"):
                if name:
                    if entry_type == "Faculty":
                        cursor.execute("INSERT INTO faculties (name, faculty_type) VALUES (?, ?)", (name, faculty_type))
                    else:
                        cursor.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
                    conn.commit()
                    st.success(f"{entry_type} added!")
                else:
                    st.error("Name cannot be empty.")

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

# --- 2. MAP FACULTIES TO SUBJECTS (TABULAR) ---
elif menu == "2. Map Faculties & Subjects":
    st.header("Map Subjects and Faculties to a Class")
    classes_df = get_classes()
    faculties_df = get_faculties()
    subjects_df = get_subjects()

    if classes_df.empty or faculties_df.empty or subjects_df.empty:
        st.warning("Please add at least one Class, Faculty, and Subject in Master Data first.")
    else:
        selected_class = st.selectbox("Select Class", classes_df['class_name'])
        class_id = classes_df.loc[classes_df['class_name'] == selected_class, 'id'].values[0]
        
        st.markdown(f"**Map up to 6 subjects for:** {selected_class}")
        
        # Prepare dropdown options
        sub_options = subjects_df['name'].tolist()
        
        # Enhance faculty options to show if they are visiting
        fac_options = []
        for _, row in faculties_df.iterrows():
            f_label = f"{row['name']} ({row['faculty_type']})" if row.get('faculty_type') else row['name']
            fac_options.append(f_label)

        # Create an editable dataframe for mapping
        df_mapping = pd.DataFrame({
            "Subject": [None] * 6,
            "Faculty": [None] * 6
        })

        with st.form("mapping_form"):
            edited_df = st.data_editor(
                df_mapping,
                column_config={
                    "Subject": st.column_config.SelectboxColumn("Subject", options=sub_options, required=True),
                    "Faculty": st.column_config.SelectboxColumn("Assigned Faculty", options=fac_options, required=True)
                },
                num_rows="fixed",
                hide_index=True
            )
            
            if st.form_submit_button("Save All Mappings"):
                # Clear old mappings for this specific class to prevent infinite duplicates
                cursor.execute("DELETE FROM faculty_subject_mapping WHERE class_id = ?", (int(class_id),))
                
                mapped_count = 0
                for index, row in edited_df.iterrows():
                    if row['Subject'] and row['Faculty']:
                        # Get IDs back from the names
                        sub_id = subjects_df.loc[subjects_df['name'] == row['Subject'], 'id'].values[0]
                        
                        # Extract raw faculty name (remove the "(Visiting)" tag for database lookup)
                        raw_fac_name = row['Faculty'].split(" (")[0]
                        fac_id = faculties_df.loc[faculties_df['name'] == raw_fac_name, 'id'].values[0]
                        
                        cursor.execute("INSERT INTO faculty_subject_mapping (class_id, faculty_id, subject_id) VALUES (?, ?, ?)", 
                                       (int(class_id), int(fac_id), int(sub_id)))
                        mapped_count += 1
                
                conn.commit()
                st.success(f"Successfully saved {mapped_count} subject-faculty mappings for this class!")

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
            cursor.execute("SELECT subject_id FROM faculty_subject_mapping WHERE class_id = ?", (int(class_id),))
            subjects = [row[0] for row in cursor.fetchall()]
            
            if not subjects:
                st.error("No subjects mapped to this class! Go to Step 2.")
            else:
                current_date = start_date
                days_scheduled = 0
                sub_idx = 0
                
                while days_scheduled < 5: 
                    date_str = current_date.strftime("%Y-%m-%d")
                    
                    if current_date.weekday() >= 5: 
                        current_date += timedelta(days=1)
                        continue
                        
                    cursor.execute("SELECT * FROM holiday_master WHERE date = ?", (date_str,))
                    if cursor.fetchone(): 
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
            
            # --- EXPORT TO EXCEL ---
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Timetable')
            
            st.download_button(
                label="📥 Export to Excel",
                data=buffer.getvalue(),
                file_name=f"Timetable_{selected_class.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )