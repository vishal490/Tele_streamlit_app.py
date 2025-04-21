import streamlit as st
import json
import os

import re

import re

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
# List your simulation files
SIM_FILES = ["Medbot.json", "Baseline1.json"]  # Update with your actual file names

selected_file = st.selectbox("Select simulation file to review", SIM_FILES)

# Load the selected simulation file
with open(selected_file, 'r') as f:
    sim_data = json.load(f)
sim_keys = list(sim_data.keys())
selected_case = st.selectbox("Select a simulation case", sim_keys)
case = sim_data.get(selected_case, {})
# # --- Load a single simulation JSON file ---
# def load_simulation(json_file_path):
#     with open(json_file_path, 'r') as f:
#         data = json.load(f)
#     return data

# # --- Main Streamlit App ---
# st.title("MedBot Simulation Doctor Review")

# # Path to your simulation JSON file (update as needed)
# JSON_FILE = "Test_simulation_doctor/Simulated_data/three_symp_noPrior_8Score_10Question.json"

# if not os.path.exists(JSON_FILE):
#     st.error(f"File '{JSON_FILE}' not found. Please check the path.")
#     st.stop()

# sim_data = load_simulation(JSON_FILE)
# sim_keys = list(sim_data.keys())

# if not sim_keys:
#     st.warning("No simulation cases found in the file.")
#     st.stop()

# selected_case = st.selectbox("Select a simulation case", sim_keys)

# case = sim_data.get(selected_case, {})

# --- Display Patient Info ---
# st.header("Patient Information")
# st.json(case.get('patient_bot', {}).get('Patient Information', {}))

# --- Display Symptoms and Prediction ---
st.subheader("Symptoms Actually Asked by MedBot (with Patient Response)")
asked_with_status = get_asked_symptoms_with_status(case.get('conversation_history', []))
if asked_with_status:
    for symptom, status in asked_with_status:
        st.write(f"{symptom}: {status}")
else:
    st.info("No explicit symptom questions found in conversation history.")
st.subheader("Chatbot Predicted Disease(s) (Top 10)")
chatbot_predictions = case.get('chatbot_predictions', {})

if chatbot_predictions:
    # Sort by probability (descending) and take the top 10
    top10 = sorted(chatbot_predictions.items(), key=lambda x: x[1], reverse=True)[:10]
    # Display as a table for clarity
    st.table(top10)
else:
    st.info("No chatbot predictions available for this case.")

# --- Display Conversation History ---
st.subheader("Conversation History")
for turn in case.get('conversation_history', []):
    role = turn.get('role', '').capitalize()
    if role.lower() == "system":
        continue  # Skip system turns
    st.markdown(f"**{role}:** {turn.get('content', '')}")


# --- Doctor Annotation Section ---
st.header("Doctor Annotation")

relevant_resp = st.radio("Were the symptom questions relevant?", ["Yes", "Partially", "No"])
asked_with_status = get_asked_symptoms_with_status(case.get('conversation_history', []))
asked_with_status=set(asked_with_status)
relevant = []
irrelevant = []

st.write("Check the relevant symptoms below. Unchecked will be considered irrelevant.")

for symptom, status in asked_with_status:
    checked = st.checkbox(f"{symptom} ({status})", key=f"rel_{symptom}")
    if checked:
        relevant.append(symptom)
    else:
        irrelevant.append(symptom)

st.text_area("Please specify any additional comments on the symptom questions.")
correct = st.radio("Was the top 10 most likely disease predicted correctly?", ["Yes", "No"])
comment = st.text_area("Additional Comments (optional)")

if st.button("Save Review"):
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

st.caption("You can review and annotate each simulation case. All reviews are saved to doctor_reviews.csv.")
