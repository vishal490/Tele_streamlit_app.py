import streamlit as st
import json
import os
import re
import ast
import re
import pandas as pd
import time

st.set_page_config(layout="wide")
# --- Custom CSS for sticky and scrollable containers ---
st.markdown("""
    <style>
    .sticky-left {
        position: sticky;
        top: 0;
        align-self: flex-start;
        z-index: 100;
        padding: 1rem 0 ;
        border-bottom: 1px solid #eee;
    }
    .sticky-top-center {
        position: sticky;
        top: 0; 
        z-index: 999;
        text-align: center;
        padding: 1rem 0;
        border-bottom: 1px solid #eee;
    }
    .sticky-top-right {
        position: sticky;
        top: 0;
        z-index: 999;
        padding: 1rem;
        border-bottom: 1px solid #eee;
    }
    .scrollable-history {
    height: 400px;
    overflow-y: auto;
    background: black;
    border: 1px solid #eee;
    padding: 1rem;
    margin-bottom: 1rem;
}
    .sticky-bottom {
        position: sticky;
        bottom: 0;  
        z-index: 999;
        padding: 1rem 0;
        border-top: 1px solid #eee;
    }
    </style>
""", unsafe_allow_html=True)

def load_reviewed_cases(review_file):
    if not os.path.exists(review_file):
        return set()
    with open(review_file, "r") as f:
        lines = f.readlines()
    reviewed = set()
    for line in lines:
        case_name = line.split(",")[0].strip()
        if case_name:
            reviewed.add(case_name)
    return reviewed

def extract_profile_and_symptoms(conversation_history):
    """
    Extracts patient profile and initial symptoms from the first user message.
    Returns (profile_dict, symptoms_list) or (None, None) if not found.
    """
    for turn in conversation_history:
        if turn.get("role") == "user":
            content = turn.get("content", "")
            match = re.search(
                r"(\{.*?\})\s*is experiencing given symptoms\s*(.*)", 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            print(match)
            if match:
                profile_str = match.group(1)
                symptoms_str = match.group(2)
                try:
                    profile = ast.literal_eval(profile_str)
                except Exception as e:
                    profile = None
                # Symptoms are comma-separated
                symptoms = [s.strip() for s in symptoms_str.split(",") if s.strip()]
                return profile, symptoms
    return None, None

def get_asked_symptoms_with_status(conversation_history):
    """
    Returns a list of (symptom, status) tuples for each symptom actually asked by MedBot,
    based on the conversation history.
    """
    asked = []
    i = 0
    while i < len(conversation_history):
        turn = conversation_history[i]
        # Find system message that asks about a symptom
        if turn.get("role") == "system":
            match = re.search(r'you should ask about ([^.\n]+)', turn.get("content", ""), re.IGNORECASE)
            if match:
                symptom = match.group(1).strip()
                # Look ahead for the next 'user' message (the patient's response)
                status = "unknown"
                for j in range(i+1, len(conversation_history)):
                    user_turn = conversation_history[j]
                    if user_turn.get("role") == "user":
                        # Try to parse "symptom:Yes" or "symptom:No"
                        user_content = user_turn.get("content", "").lower()
                        # Check for "symptom:yes" or "symptom:no"
                        if symptom.lower() in user_content:
                            if "yes" in user_content:
                                status = "present"
                            elif "no" in user_content:
                                status = "absent"
                            break
                        # Sometimes the symptom may have underscores or different spacing
                        elif user_content.startswith(symptom.lower() + ":"):
                            val = user_content.split(":", 1)[1]
                            if "yes" in val:
                                status = "present"
                            elif "no" in val:
                                status = "absent"
                            break
                asked.append((symptom, status))
        i += 1
    return asked

def clean_user_response(text):
    # Match and keep the Yes/No part, remove symptom name and colon
    # Example: "fever:No, I am not experiencing fever." -> "No, I am not experiencing fever."
    match = re.match(r"^[^:]+:\s*(Yes|No)(.*)", text, flags=re.IGNORECASE)
    if match:
        # Capitalize Yes/No for consistency
        return f"{match.group(1).capitalize()}{match.group(2)}".strip()
    return text  # Return original if pattern not matched

def get_case_display_name(case, reviewed_cases):
    if case in reviewed_cases:
        # Add green tick emoji or use green text (emoji is more universally supported)
        return f"✅ {case}"
    else:
        return case

def clean_disease_name(disease_key):
    # Remove trailing underscores/hyphens and numbers (e.g., "Flu_20230423" -> "Flu")
    cleaned = re.sub(r'[_\-]?\d+', '', disease_key)
    cleaned = cleaned.strip()
    return cleaned

def all_fields_filled(relevant_resp, correct, comment, relevant, none_relevant):
    # relevant_resp and correct are always set due to defaults
    if comment is None or comment.strip() == "":
        return False
    # Either some symptoms must be marked as relevant OR "None" must be selected
    if not relevant and not none_relevant:
        return False
    return True

def get_next_unreviewed_display_name(display_names, reviewed_cases, display_name_to_case, current_display):
    """
    Find the next unreviewed case to display after the current one.
    """
    # Convert display names to a list if it's not already
    display_names_list = list(display_names)
    
    # Find the index of the current display in the list
    try:
        current_index = display_names_list.index(current_display)
    except ValueError:
        current_index = -1
    
    # Start searching from the next item after current
    for i in range(len(display_names_list)):
        # Calculate index with wraparound
        index = (current_index + i + 1) % len(display_names_list)
        display = display_names_list[index]
        case = display_name_to_case[display]
        
        # If this case hasn't been reviewed yet, return it
        if case not in reviewed_cases:
            return display
    
    # If all cases are reviewed, return the first display name
    return display_names_list[0]

if 'next_case_to_display' not in st.session_state:
    st.session_state.next_case_to_display = None


SIM_FILES = ["Medbot.json", "Baseline1.json"]  # Update with your actual file names
selected_file = st.selectbox("Select simulation file to review", SIM_FILES)
with open(selected_file, 'r') as f:
    sim_data = json.load(f)
sim_keys = list(sim_data.keys())

review_file = f"doctor_reviews_{os.path.splitext(selected_file)[0]}.csv"
reviewed_cases = load_reviewed_cases(review_file)

# Prepare display names and mapping
display_name_to_case = {}
display_names = []
for case in sim_keys:
    display = clean_disease_name(get_case_display_name(case, reviewed_cases))
    display_names.append(display)
    display_name_to_case[display] = case

# Use the display names in the selectbox
index = 0
if st.session_state.next_case_to_display in display_names:
    index = display_names.index(st.session_state.next_case_to_display)


selected_display = st.selectbox("Select a simulation case", display_names,index=index)
selected_case = display_name_to_case[selected_display]
case = sim_data.get(selected_case, {})
asked_with_status = get_asked_symptoms_with_status(case.get('conversation_history', []))
asked_with_status=set(asked_with_status)
profile, initial_symptoms = extract_profile_and_symptoms(case.get('conversation_history', []))




# --- Layout with columns ---
col_left, col_center, col_right = st.columns([1, 2, 1])


with col_left:
    st.markdown('<div class="sticky-left">', unsafe_allow_html=True)
    
    st.header("Patient Profile")
    if profile:
        
        # Display profile as a table or key-value pairs
        for key, value in profile.items():
            if isinstance(value, dict):
                st.markdown(f"**{key.capitalize()}:**")
                for subkey, subval in value.items():
                    st.markdown(f"- {subkey.replace('_',' ').capitalize()}: {subval}")
            else:
                st.markdown(f"**{key.replace('_',' ').capitalize()}:** {value}")
    else:
        st.info("No patient profile found in the first user message.")
    st.markdown('</div>', unsafe_allow_html=True)



with col_center:
    # Initial Symptom (sticky top)
    st.markdown('<div class="sticky-top-center">', unsafe_allow_html=True)
    st.subheader("Patient came with the following Symptom")
    if initial_symptoms:
        st.markdown(", ".join(initial_symptoms))
    else:
        st.info("No initial symptoms found in the first user message.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Conversation History (scrollable)
    st.subheader("AI Doctor-Patient Conversation")
    conversation_html = '<div class="scrollable-history">'
    first_user_skipped = False
    for turn in case.get('conversation_history', []):
        role = turn.get('role', '').capitalize()
        if role.lower() == "system":
            continue
        if role.lower() == "user" and not first_user_skipped:
            first_user_skipped = True
            continue
        content = turn.get('content', '')
        if role.lower() == "user":
            content = clean_user_response(content)
        conversation_html += f"<p><b>{role}:</b> {content}</p>"
    conversation_html += "</div>"
    st.markdown(conversation_html, unsafe_allow_html=True)
    
    # Doctor Annotation (bottom)
    st.markdown('<div class="sticky-bottom">', unsafe_allow_html=True)
    # Replace your current form section with this:
    with st.form("doctor_annotation_form", clear_on_submit=True):
        st.header("Doctor Annotation")
        comment = st.text_area(
            "Please provide feedback on the AI Doctor-Patient Conversation.",
            key="comment"
        )
        relevant_resp = st.select_slider(
            "Overall how much relevant were the symptoms asked in the conversation for the given patient?",
            options=[1, 2, 3, 4, 5],
            value=3,
            format_func=lambda x: {
                1: "1 - Not at all relevant",
                2: "2 - Slightly relevant",
                3: "3 - Moderately relevant",
                4: "4 - Mostly relevant",
                5: "5 - Perfectly relevant"
            }[x],
            help="1 = Not relevant, 5 = Highly relevant",
            key="relevant_resp"
        )
        
        asked_with_status = get_asked_symptoms_with_status(case.get('conversation_history', []))
        asked_with_status = set(asked_with_status)
        relevant = []
        irrelevant = []

        st.write("Please select the symptoms below (which are asked by AI Doctor to get correct dignosis), you think are relevent symptoms for correct diagnosis. Unselected will be considered irrelevant.")

        

        # Only show individual symptom checkboxes if "None" is not selected
        
        for symptom, status in asked_with_status:
            checked = st.checkbox(f"{symptom}", key=f"rel_{symptom}")
            if checked:
                relevant.append(symptom)
            else:
                irrelevant.append(symptom)
    
        # If "None" is selected, consider all symptoms as irrelevant
        # Add a "None of the symptoms is relevant" option at the top
        none_relevant = st.checkbox("None of the symptoms is relevant", key="rel_none")
        relevant = []
        irrelevant = [symptom for symptom, _ in asked_with_status]

        correct = st.select_slider(
            "How accurate do you find the predicted disease?",
            options=[1, 2, 3, 4, 5],
            value=3,
            key="correct",
            format_func=lambda x: {
                1: "1 - Not at all Correct",
                2: "2 - Slightly Well",
                3: "3 - Moderately well",
                4: "4 - Mostly correct",
                5: "5 - Perfectly Diagnosed"
            }[x],
            help="1 = Not at all correct, 5 = Perfectly correct"
        )

        # Remove the disabled parameter
        save_review = st.form_submit_button("Save Review")

        # Move validation inside the form submission logic
        if save_review:
            if none_relevant:
                # Add a special marker in the saved data
                relevant = ["NONE_RELEVANT"]
            # Check validation after button is clicked
            if all_fields_filled(relevant_resp, correct, comment, relevant,none_relevant):
                review = {
                    "case": selected_case,
                    "relevant": relevant_resp,
                    "correct": correct,
                    "relevant_symptoms": relevant,
                    "irrelevant_symptoms": irrelevant,
                    "comment": comment
                }
                review_file = f"doctor_reviews_{os.path.splitext(selected_file)[0]}.csv"
                with open(review_file, "a") as f:
                    f.write(f"{selected_case},{relevant_resp},{correct},{'|'.join(relevant)},{'|'.join(irrelevant)},{comment}\n")
                st.success(f"Review saved to {review_file}!")
                
                next_display = get_next_unreviewed_display_name(display_names, reviewed_cases.union({selected_case}), display_name_to_case, selected_display)
                st.session_state.next_case_to_display = next_display
                
                time.sleep(1)  # Give user a moment to see the success message
                st.rerun()
            else:
                st.error("Please fill all required fields and select at least one relevant symptom.")

    st.markdown('</div>', unsafe_allow_html=True)


    

    

with col_right:
    st.markdown('<div class="sticky-top-right">', unsafe_allow_html=True)
    st.subheader("Symptoms Asked by AI Doctor and Patient Response")
    if asked_with_status:
        for symptom, status in asked_with_status:
            st.write(f"{symptom}: {status}")
    else:
        st.info("No explicit symptom questions found in conversation history.")


    st.subheader("Diseases Predicted by AI Doctor with Probabilities")
    chatbot_predictions = case.get('chatbot_predictions', {})
    if chatbot_predictions:
        top10 = sorted(chatbot_predictions.items(), key=lambda x: x[1], reverse=True)[:10]
        df = pd.DataFrame(top10, columns=["Disease Name", "Probability"])
        st.table(df)
    else:
        st.info("No chatbot predictions available for this case.")

    st.markdown('</div>', unsafe_allow_html=True)
    
    







review_file = f"doctor_reviews_{os.path.splitext(selected_file)[0]}.csv"
if os.path.exists(review_file):
    with open(review_file, "rb") as f:
        st.download_button(
            label="Download Reviews",
            data=f,
            file_name=review_file,
            mime="text/csv"
        )
        
