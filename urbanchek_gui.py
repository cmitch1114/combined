import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
from modules.john_urbanchek import UrbanchekProgram, SwimmerManager

class UrbanchekGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Urbanchek Swimming Training System")
        self.root.geometry("900x600")
        
        self.swimmer_manager = SwimmerManager()
        self.current_swimmer = None
        self.current_workout = None
        self.workout_sets = []
        self.selected_set_index = None
        
        # Create main notebook (tabbed interface)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Create tabs
        self.create_swimmers_tab()
        self.create_workouts_tab()
        self.create_results_tab()
        self.create_goal_times_tab()  # Add this line
        
        # Load data if exists
        self.load_data()

    def create_swimmers_tab(self):
        swimmers_frame = ttk.Frame(self.notebook)
        self.notebook.add(swimmers_frame, text="Swimmers")
        
        # Left side - swimmer list
        list_frame = ttk.LabelFrame(swimmers_frame, text="Swimmers")
        list_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=10, pady=10)
        
        # Swimmer listbox with scrollbar
        self.swimmer_listbox = tk.Listbox(list_frame, height=15)
        scrollbar = ttk.Scrollbar(list_frame, command=self.swimmer_listbox.yview)
        self.swimmer_listbox.configure(yscrollcommand=scrollbar.set)
        self.swimmer_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        
        # Swimmer listbox bindings
        self.swimmer_listbox.bind('<<ListboxSelect>>', self.on_select_swimmer)
        
        # Buttons for managing swimmers
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(btn_frame, text="Add Swimmer", command=self.add_swimmer).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Remove Swimmer", command=self.remove_swimmer).pack(side=tk.LEFT, padx=5)
        
        # Right side - swimmer details
        details_frame = ttk.LabelFrame(swimmers_frame, text="Swimmer Details")
        details_frame.pack(side=tk.RIGHT, fill="both", expand=True, padx=10, pady=10)
        
        # 400m time input
        time_frame = ttk.Frame(details_frame)
        time_frame.pack(fill="x", pady=10)
        ttk.Label(time_frame, text="400m Time:").pack(side=tk.LEFT, padx=5)
        
        self.min_var = tk.StringVar()
        self.sec_var = tk.StringVar()
        
        ttk.Entry(time_frame, width=3, textvariable=self.min_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="min").pack(side=tk.LEFT, padx=2)
        ttk.Entry(time_frame, width=5, textvariable=self.sec_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="sec").pack(side=tk.LEFT, padx=2)
        
        ttk.Button(time_frame, text="Set Time", command=self.set_400m_time).pack(side=tk.LEFT, padx=10)
        
        # Stroke selection
        stroke_frame = ttk.Frame(details_frame)
        stroke_frame.pack(fill="x", pady=10)
        ttk.Label(stroke_frame, text="Primary Stroke:").pack(side=tk.LEFT, padx=5)
        self.stroke_var = tk.StringVar(value="Freestyle")
        stroke_combo = ttk.Combobox(stroke_frame, textvariable=self.stroke_var, 
                                   values=["Freestyle", "Backstroke", "Breaststroke", "Butterfly", "IM"])
        stroke_combo.pack(side=tk.LEFT, padx=5)
        stroke_combo.bind("<<ComboboxSelected>>", self.update_paces)
        
        # Distance selection for pace calculation
        distance_frame = ttk.Frame(details_frame)
        distance_frame.pack(fill="x", pady=10)
        ttk.Label(distance_frame, text="Calculate paces for:").pack(side=tk.LEFT, padx=5)
        self.distance_base_var = tk.StringVar(value="100m")
        distance_combo = ttk.Combobox(distance_frame, textvariable=self.distance_base_var, 
                                     values=["25m", "50m", "100m", "200m", "500m", "1000m"])
        distance_combo.pack(side=tk.LEFT, padx=5)
        distance_combo.bind("<<ComboboxSelected>>", self.update_paces)
        
        # Zone paces display
        self.zone_frame = ttk.LabelFrame(details_frame, text="Zone Paces")
        self.zone_frame.pack(fill="both", expand=True, pady=5)
        
        # Add zone descriptions
        zone_descriptions = {
            "White": "Recovery (110% of base pace)",
            "Pink": "Aerobic/Endurance (105% of base pace)",
            "Red": "Threshold (100% of base pace)",
            "Blue": "VO2 Max (95% of base pace)",
            "Purple": "Anaerobic/Sprint (90% of base pace)"
        }
        
        self.zone_labels = {}
        for i, (zone, description) in enumerate(zone_descriptions.items()):
            frame = ttk.Frame(self.zone_frame)
            frame.pack(fill="x", pady=2)
            
            # Create a colored square indicator (20x20 pixels)
            color_indicator = tk.Canvas(frame, width=15, height=15, highlightthickness=0)
            color_indicator.pack(side=tk.LEFT, padx=5)
            color_indicator.create_rectangle(0, 0, 15, 15, fill=zone.lower())
            
            # Zone name with description
            ttk.Label(frame, text=f"{zone}:", width=7).pack(side=tk.LEFT)
            ttk.Label(frame, text=description, width=30).pack(side=tk.LEFT, padx=5)
            
            # Pace value (will be updated when swimmer selected)
            self.zone_labels[zone] = ttk.Label(frame, text="-")
            self.zone_labels[zone].pack(side=tk.LEFT, padx=5)

    def create_workouts_tab(self):
        workouts_frame = ttk.Frame(self.notebook)
        self.notebook.add(workouts_frame, text="Workouts")
        
        # Top section - Current swimmer and workout creation
        top_frame = ttk.LabelFrame(workouts_frame, text="Create Workout")
        top_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(top_frame, text="Current Swimmer:").grid(row=0, column=0, padx=5, pady=5)
        self.current_swimmer_label = ttk.Label(top_frame, text="None selected")
        self.current_swimmer_label.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Workout Name:").grid(row=1, column=0, padx=5, pady=5)
        self.workout_name_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.workout_name_var, width=30).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(top_frame, text="Create Workout", command=self.create_workout).grid(row=1, column=2, padx=5, pady=5)
        
        # Set creation section
        set_frame = ttk.LabelFrame(workouts_frame, text="Add Sets")
        set_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Set parameters
        params_frame = ttk.Frame(set_frame)
        params_frame.pack(fill="x", pady=5)
        
        ttk.Label(params_frame, text="Distance (m):").grid(row=0, column=0, padx=5, pady=5)
        self.distance_var = tk.StringVar()
        ttk.Entry(params_frame, textvariable=self.distance_var, width=5).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(params_frame, text="Zone:").grid(row=0, column=2, padx=5, pady=5)
        self.zone_var = tk.StringVar()
        zone_combo = ttk.Combobox(params_frame, textvariable=self.zone_var, values=["White", "Pink", "Red", "Blue", "Purple"])
        zone_combo.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(params_frame, text="Stroke:").grid(row=0, column=4, padx=5, pady=5)
        self.set_stroke_var = tk.StringVar(value="Freestyle")
        stroke_combo = ttk.Combobox(params_frame, textvariable=self.set_stroke_var, 
                                   values=["Freestyle", "Backstroke", "Breaststroke", "Butterfly", "IM"])
        stroke_combo.grid(row=0, column=5, padx=5, pady=5)

        ttk.Label(params_frame, text="Reps:").grid(row=0, column=6, padx=5, pady=5)
        self.reps_var = tk.StringVar()
        ttk.Entry(params_frame, textvariable=self.reps_var, width=3).grid(row=0, column=7, padx=5, pady=5)
        
        ttk.Label(params_frame, text="Rest (sec):").grid(row=0, column=8, padx=5, pady=5)
        self.rest_var = tk.StringVar()
        ttk.Entry(params_frame, textvariable=self.rest_var, width=4).grid(row=0, column=9, padx=5, pady=5)
        
        ttk.Button(params_frame, text="Add Set", command=self.add_set).grid(row=0, column=10, padx=15, pady=5)
        
        # Current sets display
        self.sets_frame = ttk.LabelFrame(set_frame, text="Current Sets")
        self.sets_frame.pack(fill="both", expand=True, pady=10)
        
        self.sets_tree = ttk.Treeview(self.sets_frame, 
                             columns=("index", "distance", "zone", "stroke", "reps", "rest"), 
                             show="headings")
        self.sets_tree.heading("index", text="#")
        self.sets_tree.heading("distance", text="Distance (m)")
        self.sets_tree.heading("zone", text="Zone")
        self.sets_tree.heading("stroke", text="Stroke")
        self.sets_tree.heading("reps", text="Reps")
        self.sets_tree.heading("rest", text="Rest (sec)")
        
        self.sets_tree.column("index", width=30)
        self.sets_tree.column("distance", width=80)
        self.sets_tree.column("zone", width=80)
        self.sets_tree.column("stroke", width=80)
        self.sets_tree.column("reps", width=50)
        self.sets_tree.column("rest", width=70)
        
        self.sets_tree.pack(fill="both", expand=True)
        self.sets_tree.bind('<<TreeviewSelect>>', self.on_select_set)
        
        buttons_frame = ttk.Frame(self.sets_frame)
        buttons_frame.pack(fill="x", pady=5)
        ttk.Button(buttons_frame, text="Remove Set", command=self.remove_set).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Clear All", command=self.clear_sets).pack(side=tk.LEFT, padx=5)

    def create_results_tab(self):
        results_frame = ttk.Frame(self.notebook)
        self.notebook.add(results_frame, text="Results")
        
        # Top controls
        controls_frame = ttk.Frame(results_frame)
        controls_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(controls_frame, text="Current Swimmer:").grid(row=0, column=0, padx=5, pady=5)
        self.results_swimmer_label = ttk.Label(controls_frame, text="None selected")
        self.results_swimmer_label.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(controls_frame, text="Select Set:").grid(row=1, column=0, padx=5, pady=5)
        self.set_select_var = tk.StringVar()
        self.set_select_combobox = ttk.Combobox(controls_frame, textvariable=self.set_select_var)
        self.set_select_combobox.grid(row=1, column=1, padx=5, pady=5)
        self.set_select_combobox.bind('<<ComboboxSelected>>', self.on_select_result_set)
        
        # Time entries section
        time_frame = ttk.LabelFrame(results_frame, text="Enter Times")
        time_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.time_entries_frame = ttk.Frame(time_frame)
        self.time_entries_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Time entries will be added dynamically
        self.time_entries = []
        
        # Submit button
        submit_frame = ttk.Frame(time_frame)
        submit_frame.pack(fill="x", pady=10)
        ttk.Button(submit_frame, text="Submit Times", command=self.submit_times).pack()
        
        # Results display
        self.results_display_frame = ttk.LabelFrame(results_frame, text="Results")
        self.results_display_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.results_text = tk.Text(self.results_display_frame, wrap=tk.WORD)
        self.results_text.pack(fill="both", expand=True)
        self.results_text.config(state=tk.DISABLED)

    def create_goal_times_tab(self):
        goal_times_frame = ttk.Frame(self.notebook)
        self.notebook.add(goal_times_frame, text="Goal Times")
        
        # Current swimmer display
        top_frame = ttk.Frame(goal_times_frame)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="Current Swimmer:").pack(side=tk.LEFT, padx=5)
        self.goal_swimmer_label = ttk.Label(top_frame, text="None selected")
        self.goal_swimmer_label.pack(side=tk.LEFT, padx=5)
        
        # Create a frame with two columns
        content_frame = ttk.Frame(goal_times_frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Left column - Event selection and time input
        left_frame = ttk.LabelFrame(content_frame, text="Set Goal Time")
        left_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=5)
        
        # Event selection
        event_frame = ttk.Frame(left_frame)
        event_frame.pack(fill="x", pady=10)
        
        ttk.Label(event_frame, text="Select Event:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.event_var = tk.StringVar()
        events = [
            "100 Free", "200 Free", "400 Free", "500 Free",
            "100 Back", "200 Back",
            "100 Fly", "200 Fly",
            "100 Breast", "200 Breast",
            "200 IM", "400 IM"
        ]
        event_combo = ttk.Combobox(event_frame, textvariable=self.event_var, values=events, width=15)
        event_combo.grid(row=0, column=1, padx=5, pady=5)
        event_combo.bind("<<ComboboxSelected>>", self.on_event_selected)
        
        # Goal time input
        time_frame = ttk.Frame(left_frame)
        time_frame.pack(fill="x", pady=10)
        
        ttk.Label(time_frame, text="Goal Time:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        time_input_frame = ttk.Frame(time_frame)
        time_input_frame.grid(row=0, column=1, padx=5, pady=5)
        
        self.goal_min_var = tk.StringVar()
        ttk.Entry(time_input_frame, width=3, textvariable=self.goal_min_var).pack(side=tk.LEFT)
        ttk.Label(time_input_frame, text="min").pack(side=tk.LEFT, padx=2)
        
        self.goal_sec_var = tk.StringVar()
        ttk.Entry(time_input_frame, width=5, textvariable=self.goal_sec_var).pack(side=tk.LEFT)
        ttk.Label(time_input_frame, text="sec").pack(side=tk.LEFT, padx=2)
        
        # Calculate button
        ttk.Button(left_frame, text="Calculate Splits", command=self.calculate_goal_splits).pack(pady=15)
        
        # Right column - Results display
        right_frame = ttk.LabelFrame(content_frame, text="Goal Splits")
        right_frame.pack(side=tk.RIGHT, fill="both", expand=True, padx=5, pady=5)
        
        # Create a frame for splits display
        self.splits_frame = ttk.Frame(right_frame)
        self.splits_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create a scrollable text widget for displaying the results
        self.splits_text = tk.Text(self.splits_frame, wrap=tk.WORD, height=20, width=40)
        scrollbar = ttk.Scrollbar(self.splits_frame, command=self.splits_text.yview)
        self.splits_text.configure(yscrollcommand=scrollbar.set)
        
        self.splits_text.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        
        # Initially disable the text widget
        self.splits_text.config(state=tk.DISABLED)

    # Helper methods
    def format_time(self, seconds):
        """Convert seconds to min:sec format"""
        minutes = int(seconds // 60)
        secs = round(seconds % 60, 1)
        return f"{minutes}:{secs:04.1f}" if secs >= 10 else f"{minutes}:0{secs:.1f}"
    
    def parse_time(self, min_str, sec_str):
        """Convert min:sec format to seconds"""
        try:
            minutes = int(min_str) if min_str.strip() else 0
            seconds = float(sec_str) if sec_str.strip() else 0
            return minutes * 60 + seconds
        except ValueError:
            return None
    
    # Event handlers
    def on_select_swimmer(self, event):
        if not self.swimmer_listbox.curselection():
            return
        
        index = self.swimmer_listbox.curselection()[0]
        name = self.swimmer_listbox.get(index)
        
        try:
            self.current_swimmer = self.swimmer_manager.get_swimmer(name)
            self.current_swimmer_label.config(text=name)
            self.results_swimmer_label.config(text=name)
            self.goal_swimmer_label.config(text=name)  # Add this line
            
            # Update zone paces display
            if self.current_swimmer.four_hundred_time:
                for zone in self.zone_labels:
                    pace = self.current_swimmer.get_zone_pace(zone)
                    self.zone_labels[zone].config(text=self.format_time(pace))
            else:
                for zone in self.zone_labels:
                    self.zone_labels[zone].config(text="-")
            
            # Update results tab
            self.update_results_tab()
            
        except ValueError as e:
            messagebox.showerror("Error", str(e))
    
    def on_select_set(self, event):
        selection = self.sets_tree.selection()
        if selection:
            self.selected_set_index = int(self.sets_tree.item(selection[0])['values'][0]) - 1
    
    def on_select_result_set(self, event):
        if not self.current_workout or self.set_select_var.get() == '':
            return
        
        set_index = int(self.set_select_var.get().split()[1]) - 1
        if set_index < 0 or set_index >= len(self.current_workout["sets"]):
            return
        
        self.create_time_entries(set_index)
    
    def add_swimmer(self):
        name = simpledialog.askstring("Add Swimmer", "Enter swimmer name:")
        if not name:
            return
        
        try:
            self.swimmer_manager.add_swimmer(name)
            self.refresh_swimmer_list()
            self.save_data()
        except ValueError as e:
            messagebox.showerror("Error", str(e))
    
    def remove_swimmer(self):
        if not self.swimmer_listbox.curselection():
            messagebox.showinfo("Info", "No swimmer selected")
            return
        
        index = self.swimmer_listbox.curselection()[0]
        name = self.swimmer_listbox.get(index)
        
        try:
            self.swimmer_manager.remove_swimmer(name)
            self.refresh_swimmer_list()
            
            if self.current_swimmer and self.current_swimmer.swimmer_name == name:
                self.current_swimmer = None
                self.current_swimmer_label.config(text="None selected")
                self.results_swimmer_label.config(text="None selected")
            
            self.save_data()
        except ValueError as e:
            messagebox.showerror("Error", str(e))
    
    def set_400m_time(self):
        if not self.current_swimmer:
            messagebox.showinfo("Info", "No swimmer selected")
            return
        
        min_str = self.min_var.get()
        sec_str = self.sec_var.get()
        
        time_seconds = self.parse_time(min_str, sec_str)
        if time_seconds is None:
            messagebox.showerror("Error", "Invalid time format")
            return
        
        minutes = int(time_seconds // 60)
        seconds = time_seconds % 60
        
        self.current_swimmer.set_four_hundred_time(minutes, seconds)
        
        # Update paces based on current stroke and distance
        self.update_paces()
        
        self.save_data()
    
    def create_workout(self):
        if not self.current_swimmer:
            messagebox.showinfo("Info", "No swimmer selected")
            return
        
        name = self.workout_name_var.get()
        if not name:
            messagebox.showinfo("Info", "Please enter a workout name")
            return
        
        if not self.workout_sets:
            messagebox.showinfo("Info", "No sets added to workout")
            return
        
        # Create the workout
        self.current_workout = self.current_swimmer.create_workout(name, self.workout_sets.copy())
        
        # Reset the form and update the results tab
        self.workout_name_var.set("")
        self.clear_sets()
        self.update_results_tab()
        
        messagebox.showinfo("Success", f"Workout '{name}' created successfully")
    
    def add_set(self):
        try:
            distance = int(self.distance_var.get())
            zone = self.zone_var.get()
            stroke = self.set_stroke_var.get()
            reps = int(self.reps_var.get())
            rest = int(self.rest_var.get())
            
            if not zone:
                messagebox.showinfo("Info", "Please select a zone")
                return
            
            if zone not in ["White", "Pink", "Red", "Blue", "Purple"]:
                messagebox.showinfo("Info", "Invalid zone")
                return
            
            # Create the set
            set_data = {
                "distance": distance,
                "zone": zone,
                "stroke": stroke,
                "reps": reps,
                "rest": rest
            }
            
            self.workout_sets.append(set_data)
            
            # Add to the tree
            self.sets_tree.insert("", tk.END, values=(
                len(self.workout_sets),
                distance,
                zone,
                stroke,
                reps,
                rest
            ))
            
            # Reset inputs
            self.distance_var.set("")
            self.zone_var.set("")
            # Keep the stroke selection as is for convenience
            self.reps_var.set("")
            self.rest_var.set("")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter valid values for all fields")
    
    def remove_set(self):
        if self.selected_set_index is None:
            messagebox.showinfo("Info", "No set selected")
            return
        
        self.workout_sets.pop(self.selected_set_index)
        self.refresh_sets_tree()
        self.selected_set_index = None
    
    def clear_sets(self):
        self.workout_sets = []
        self.refresh_sets_tree()
        self.selected_set_index = None
    
    def refresh_sets_tree(self):
        # Clear the tree
        for item in self.sets_tree.get_children():
            self.sets_tree.delete(item)
        
        # Add all sets
        for i, set_data in enumerate(self.workout_sets):
            self.sets_tree.insert("", tk.END, values=(
                i + 1,
                set_data["distance"],
                set_data["zone"],
                set_data.get("stroke", "Freestyle"),  # Default to freestyle if not specified
                set_data["reps"],
                set_data["rest"]
            ))
    
    def update_results_tab(self):
        if not self.current_swimmer or not hasattr(self.current_swimmer, 'workouts'):
            self.set_select_combobox.config(values=[])
            self.set_select_var.set("")
            self.clear_time_entries()
            return
        
        # Get workouts for the current swimmer
        if hasattr(self.current_swimmer, 'workouts') and self.current_swimmer.workouts:
            workout = self.current_swimmer.workouts[-1]  # Get the latest workout
            self.current_workout = workout
            
            # Update set selection dropdown
            set_options = [f"Set {i+1}" for i in range(len(workout["sets"]))]
            self.set_select_combobox.config(values=set_options)
            
            if set_options:
                self.set_select_var.set(set_options[0])
                self.create_time_entries(0)
        else:
            self.set_select_combobox.config(values=[])
            self.set_select_var.set("")
            self.clear_time_entries()
    
    def create_time_entries(self, set_index):
        self.clear_time_entries()
        
        if not self.current_workout:
            return
        
        set_data = self.current_workout["sets"][set_index]
        reps = set_data["reps"]
        
        # Create entries for each rep
        for i in range(reps):
            frame = ttk.Frame(self.time_entries_frame)
            frame.pack(fill="x", pady=2)
            
            ttk.Label(frame, text=f"Rep {i+1}:").pack(side=tk.LEFT, padx=5)
            
            min_var = tk.StringVar()
            min_entry = ttk.Entry(frame, width=3, textvariable=min_var)
            min_entry.pack(side=tk.LEFT)
            
            ttk.Label(frame, text="min").pack(side=tk.LEFT, padx=2)
            
            sec_var = tk.StringVar()
            sec_entry = ttk.Entry(frame, width=5, textvariable=sec_var)
            sec_entry.pack(side=tk.LEFT)
            
            ttk.Label(frame, text="sec").pack(side=tk.LEFT, padx=2)
            
            self.time_entries.append((min_var, sec_var))
            
        # Check if times already exist
        if "actual_times" in set_data:
            for i, time in enumerate(set_data["actual_times"]):
                if i < len(self.time_entries):
                    minutes = int(time // 60)
                    seconds = time % 60
                    self.time_entries[i][0].set(str(minutes))
                    self.time_entries[i][1].set(f"{seconds:.1f}")
    
    def clear_time_entries(self):
        for widget in self.time_entries_frame.winfo_children():
            widget.destroy()
        
        self.time_entries = []
    
    def submit_times(self):
        if not self.current_swimmer or not self.current_workout:
            messagebox.showinfo("Info", "No workout selected")
            return
        
        if not self.set_select_var.get():
            messagebox.showinfo("Info", "No set selected")
            return
        
        set_index = int(self.set_select_var.get().split()[1]) - 1
        
        # Parse times
        times = []
        for min_var, sec_var in self.time_entries:
            time_seconds = self.parse_time(min_var.get(), sec_var.get())
            if time_seconds is None:
                messagebox.showerror("Error", "Invalid time format")
                return
            
            times.append(time_seconds)
        
        # Log times
        self.current_swimmer.log_set_times(self.current_workout, set_index, times)
        
        # Analyze workout and display results
        analyzed_workout = self.current_swimmer.analyze_workout(self.current_workout)
        self.display_workout_results(analyzed_workout)
        
        self.save_data()
        
        messagebox.showinfo("Success", "Times submitted successfully")
    
    # Add the stroke information to the results display
    def display_workout_results(self, workout):
        # Clear previous results
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        
        # Display workout results
        self.results_text.insert(tk.END, f"Workout: {workout['name']}\n\n")
        
        for set_index, set_data in enumerate(workout["sets"]):
            self.results_text.insert(tk.END, f"Set {set_index + 1}:\n")
            self.results_text.insert(tk.END, f"  Distance: {set_data['distance']}m\n")
            self.results_text.insert(tk.END, f"  Zone: {set_data['zone']}\n")
            self.results_text.insert(tk.END, f"  Stroke: {set_data.get('stroke', 'Freestyle')}\n")  # Add this line
            self.results_text.insert(tk.END, f"  Reps: {set_data['reps']}\n")
            self.results_text.insert(tk.END, f"  Rest: {set_data['rest']}s\n")
            
            if "actual_times" in set_data:
                self.results_text.insert(tk.END, "  Times:\n")
                for i, time in enumerate(set_data["actual_times"]):
                    formatted_time = self.format_time(time)
                    self.results_text.insert(tk.END, f"    Rep {i+1}: {formatted_time}\n")
                
                if "average_time" in set_data:
                    avg_time = self.format_time(set_data["average_time"])
                    self.results_text.insert(tk.END, f"  Average Time: {avg_time}\n")
                
                if "target_pace" in set_data:
                    target_pace = self.format_time(set_data["target_pace"])
                    self.results_text.insert(tk.END, f"  Target Pace: {target_pace}\n")
                    
                if "pace_difference" in set_data:
                    diff = set_data["pace_difference"]
                    diff_str = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
                    self.results_text.insert(tk.END, f"  Pace Difference: {diff_str}\n")
            
            self.results_text.insert(tk.END, "\n")
        
        self.results_text.insert(tk.END, "\nZone Paces:\n")
        for zone in ["White", "Pink", "Red", "Blue", "Purple"]:
            pace = self.current_swimmer.get_zone_pace(zone)
            self.results_text.insert(tk.END, f"  {zone} Zone: {self.format_time(pace)}\n")
        
        self.results_text.config(state=tk.DISABLED)
    
    def refresh_swimmer_list(self):
        self.swimmer_listbox.delete(0, tk.END)
        for name in self.swimmer_manager.list_swimmers():
            self.swimmer_listbox.insert(tk.END, name)
    
    def save_data(self):
        # Implement data saving
        pass
    
    def load_data(self):
        # Implement data loading
        self.refresh_swimmer_list()

    def update_paces(self, event=None):
        """Update paces when stroke or distance changes"""
        if not self.current_swimmer or not self.current_swimmer.four_hundred_time:
            return
        
        # Recalculate paces based on stroke and distance
        stroke = self.stroke_var.get()
        distance_base = self.distance_base_var.get()
        
        # Update zone paces display
        for zone in self.zone_labels:
            # Get base pace for 100m
            pace_100m = self.current_swimmer.get_zone_pace(zone)
            
            # Apply stroke factor
            stroke_factors = {
                "Freestyle": 1.0,
                "Backstroke": 1.10,  # 10% slower than freestyle
                "Butterfly": 1.15,   # 15% slower 
                "Breaststroke": 1.25, # 25% slower
                "IM": 1.15           # 15% slower (average)
            }
            
            stroke_factor = stroke_factors.get(stroke, 1.0)
            adjusted_pace = pace_100m * stroke_factor
            
            # Apply distance factor
            distance_factors = {
                "25m": 0.24,    # Slightly faster per 25 than just quarter of 100
                "50m": 0.5,     # Half of 100m pace
                "100m": 1.0,    # Base
                "200m": 2.05,   # Slightly more than double
                "500m": 5.2,    # Slightly more than 5x
                "1000m": 10.5   # Slightly more than 10x
            }
            
            # Extract numeric value from the distance string
            distance_value = int(''.join(filter(str.isdigit, distance_base)))
            
            # Apply the appropriate distance factor
            distance_factor = distance_factors.get(distance_base, distance_value/100)
            final_pace = adjusted_pace * distance_factor
            
            # Update label
            self.zone_labels[zone].config(text=self.format_time(final_pace))

    def log_set_times(self, workout, set_index, times):
        """Log actual times for a set in a workout"""
        if 0 <= set_index < len(workout["sets"]):
            workout["sets"][set_index]["actual_times"] = times
            
            # Calculate average time
            avg_time = sum(times) / len(times)
            workout["sets"][set_index]["average_time"] = avg_time
            
            # Calculate target pace based on zone and stroke
            set_distance = workout["sets"][set_index]["distance"]
            set_zone = workout["sets"][set_index]["zone"]
            set_stroke = workout["sets"][set_index].get("stroke", "Freestyle")
            zone_pace = self.get_zone_pace(set_zone)
            
            if zone_pace:
                # Apply stroke factor
                stroke_factors = {
                    "Freestyle": 1.0,
                    "Backstroke": 1.10,
                    "Butterfly": 1.15,
                    "Breaststroke": 1.25,
                    "IM": 1.15
                }
                
                stroke_factor = stroke_factors.get(set_stroke, 1.0)
                adjusted_pace = zone_pace * stroke_factor
                
                # Convert zone pace (per 100m) to target time for this distance
                target_time = adjusted_pace * (set_distance / 100)
                workout["sets"][set_index]["target_pace"] = target_time
                
                # Calculate difference between actual and target pace
                pace_diff = ((avg_time - target_time) / target_time) * 100
                workout["sets"][set_index]["pace_difference"] = pace_diff

    def on_event_selected(self, event):
        """Handle event selection in the Goal Times tab"""
        # Clear previous goal time
        self.goal_min_var.set("")
        self.goal_sec_var.set("")
        
        # Clear previous splits display
        self.clear_splits_display()

    def clear_splits_display(self):
        """Clear the splits display text widget"""
        self.splits_text.config(state=tk.NORMAL)
        self.splits_text.delete(1.0, tk.END)
        self.splits_text.config(state=tk.DISABLED)

    def calculate_goal_splits(self):
        """Calculate and display goal splits based on selected event and time"""
        if not self.current_swimmer:
            messagebox.showinfo("Info", "No swimmer selected")
            return
        
        event = self.event_var.get()
        if not event:
            messagebox.showinfo("Info", "Please select an event")
            return
        
        # Parse the goal time
        min_str = self.goal_min_var.get()
        sec_str = self.goal_sec_var.get()
        
        goal_time_seconds = self.parse_time(min_str, sec_str)
        if goal_time_seconds is None:
            messagebox.showerror("Error", "Invalid time format")
            return
        
        # Calculate splits based on the event
        splits = self.calculate_splits_for_event(event, goal_time_seconds)
        
        # Display the results
        self.display_goal_splits(event, goal_time_seconds, splits)
        
    def calculate_splits_for_event(self, event, goal_time_seconds):
        """Calculate splits based on event and goal time"""
        splits = []
        
        # Define split percentages for each event
        # These percentages are based on your Excel formulas
        split_percentages = {
            "100 Free": [0.4783, 0.5215],
            "200 Free": [0.2335, 0.2543, 0.2562, 0.2556],
            "400 Free": [0.233, 0.255, 0.2558, 0.2562],
            "500 Free": [0.1925, 0.2025, 0.2027, 0.2035, 0.1988],
            "100 Back": [0.4746, 0.5252],
            "200 Back": [0.2323, 0.2529, 0.2539, 0.2606],
            "100 Fly": [0.4692, 0.5307],
            "200 Fly": [0.2278, 0.2559, 0.2561, 0.2599],
            "100 Breast": [0.4697, 0.5301],
            "200 Breast": [0.2304, 0.2547, 0.2567, 0.2578],
            "200 IM": [0.2258, 0.2561, 0.2895, 0.2287],
            "400 IM": [0.2282, 0.2561, 0.287, 0.2286]
        }
        
        if event in split_percentages:
            for percentage in split_percentages[event]:
                split_time = goal_time_seconds * percentage
                splits.append(split_time)
        
        return splits

    def display_goal_splits(self, event, goal_time_seconds, splits):
        """Display the calculated splits"""
        self.splits_text.config(state=tk.NORMAL)
        self.splits_text.delete(1.0, tk.END)
        
        # Format the goal time
        goal_time_formatted = self.format_time(goal_time_seconds)
        
        # Add goal time header
        self.splits_text.insert(tk.END, f"{event} Goal Time: {goal_time_formatted}\n\n")
        
        # Display splits based on the event
        if event in ["100 Free", "100 Back", "100 Fly", "100 Breast"]:
            # 100s have 2 splits (50s)
            self.splits_text.insert(tk.END, "Split breakdowns (by 50):\n\n")
            for i, split in enumerate(splits):
                self.splits_text.insert(tk.END, f"50 #{i+1}: {self.format_time(split)}\n")
                
        elif event in ["200 Free", "200 Back", "200 Fly", "200 Breast"]:
            # 200s have 4 splits (50s)
            self.splits_text.insert(tk.END, "Split breakdowns (by 50):\n\n")
            for i, split in enumerate(splits):
                self.splits_text.insert(tk.END, f"50 #{i+1}: {self.format_time(split)}\n")
            
            # Also show 100 splits if possible
            if len(splits) >= 4:
                self.splits_text.insert(tk.END, "\nBy 100s:\n")
                self.splits_text.insert(tk.END, f"First 100: {self.format_time(splits[0] + splits[1])}\n")
                self.splits_text.insert(tk.END, f"Second 100: {self.format_time(splits[2] + splits[3])}\n")
        
        elif event in ["400 Free", "500 Free"]:
            # Show 100 splits for 400/500
            distances = 100 if event == "400 Free" else 100
            self.splits_text.insert(tk.END, f"Split breakdowns (by {distances}):\n\n")
            for i, split in enumerate(splits):
                self.splits_text.insert(tk.END, f"{distances} #{i+1}: {self.format_time(split)}\n")
        
        elif event == "200 IM":
            # 200 IM has 4 splits (50s) with stroke names
            strokes = ["Fly", "Back", "Breast", "Free"]
            self.splits_text.insert(tk.END, "Split breakdowns (by 50):\n\n")
            for i, (split, stroke) in enumerate(zip(splits, strokes)):
                self.splits_text.insert(tk.END, f"50 {stroke}: {self.format_time(split)}\n")
        
        elif event == "400 IM":
            # 400 IM has 4 splits (100s) with stroke names
            strokes = ["Fly", "Back", "Breast", "Free"]
            self.splits_text.insert(tk.END, "Split breakdowns (by 100):\n\n")
            for i, (split, stroke) in enumerate(zip(splits, strokes)):
                self.splits_text.insert(tk.END, f"100 {stroke}: {self.format_time(split)}\n")
        
        # Add cumulative times if there are more than 2 splits
        if len(splits) > 2:
            self.splits_text.insert(tk.END, "\nCumulative times:\n")
            cumulative = 0
            for i, split in enumerate(splits):
                cumulative += split
                distance = (i + 1) * (100 if event in ["400 Free", "500 Free", "400 IM"] else 50)
                self.splits_text.insert(tk.END, f"@ {distance}: {self.format_time(cumulative)}\n")
        
        self.splits_text.config(state=tk.DISABLED)

# Main app startup
if __name__ == "__main__":
    root = tk.Tk()
    app = UrbanchekGUI(root)
    root.mainloop()