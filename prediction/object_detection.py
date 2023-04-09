import os
import io
import time
import subprocess
from typing import Sequence
import threading
import openai
from google.cloud import vision

def analyze_image_from_uri(
    image: vision.Image,
    feature_types: Sequence,
) -> vision.AnnotateImageResponse:
    client = vision.ImageAnnotatorClient()

    features = [vision.Feature(type_=feature_type) for feature_type in feature_types]
    request = vision.AnnotateImageRequest(image=image, features=features)

    response = client.annotate_image(request=request)

    return response

def get_unique_labels_list(response: vision.AnnotateImageResponse):
    label_list = [label.description for label in response.label_annotations]
    unique_labels = []
    [unique_labels.append(label) for label in label_list if label not in unique_labels and "design" not in label]
    return unique_labels

def get_labels_description(unique_labels: list):
    # for label in response.label_annotations:
    #     print(
    #         f"{label.score:4.0%}",
    #         f"{label.description:5}",
    #         sep=" | ",
    #     )
    return "--- Environment Description ---\n" + ", ".join(unique_labels)

def get_unique_objects_list(response: vision.AnnotateImageResponse):
    object_list = [obj.name for obj in response.localized_object_annotations]
    unique_objects = []
    [unique_objects.append(obj) for obj in object_list if obj not in unique_objects]
    return unique_objects

def get_objects_description(unique_objects: list):
    # for obj in response.localized_object_annotations:
    #     nvertices = obj.bounding_poly.normalized_vertices
    #     print(
    #         f"{obj.score:4.0%}",
    #         f"{obj.name:15}",
    #         f"{obj.mid:10}",
    #         ",".join(f"({v.x:.1f},{v.y:.1f})" for v in nvertices),
    #         sep=" | ",
    #     )
    return "--- Surrounding Objects ---\n" + ", ".join(unique_objects)

def get_current_foreground_app_name():
    output = subprocess.check_output(["lsappinfo info -only LSBundlePath `lsappinfo front`"], shell=True).decode("utf-8")
    return output.split("/")[-1][:-6]

app_data_lock = threading.Lock()
app_time_usage = []
context_data_lock = threading.Lock()
context_data_condition = threading.Condition(context_data_lock)
context_description = None

# A function that runs in a child thread and fetches the name of the foreground application every 1 minute
def fetch_foreground_app_name():
    time_sum = 0
    current_app = None
    while True:
        app_name = get_current_foreground_app_name()
        app_data_lock.acquire()
        if app_name == current_app:
            app_time_usage[-1]["time_used"] += 1
        else:
            app_time_usage.append({"app_name":app_name, "time_used": 1})
        if (time_sum + 1 > 60):
            if app_time_usage[0]["time_used"] > 1:
                app_time_usage[0]["time_used"] -= 1
            else:
                app_time_usage.pop(0)
        app_data_lock.release()
        current_app = app_name
        time_sum += 1
        time.sleep(1) # wait for 1 second before fetching the name of the foreground application again

def start_fetching_app_names():
    thread = threading.Thread(target=fetch_foreground_app_name)
    thread.setDaemon(True)
    thread.start()

def get_app_activity():
    app_data_lock.acquire()
    app_time = app_time_usage.copy()
    app_data_lock.release()
    trace_text = "\n".join([f'Used \"{item["app_name"]}\" for {item["time_used"]} min' for item in app_time])
    return "--- Activity in chronological order --- \n" + trace_text

def ChatGPT_conversation(conversation):
    model_id = 'gpt-3.5-turbo'
    response = openai.ChatCompletion.create(
        model=model_id,
        messages=conversation
    )
    # api_usage = response['usage']
    # print('Total token consumed: {0}'.format(api_usage['total_tokens']))
    # stop means complete
    # print(response['choices'][0].finish_reason)
    # print(response['choices'][0].index)
    conversation.append({'role': response.choices[0].message.role, 'content': response.choices[0].message.content})
    return conversation

def ask_gpt(prompt):
    openai.api_key = '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'
    conversation = []
    conversation.append({'role': 'system', 'content': "Hi! I am a language model developed by OpenAI to analyze people's behaviors based on relevant context details. How can I assist you today?"})
    conversation.append({'role': 'user', 'content': prompt})
    conversation = ChatGPT_conversation(conversation)
    return conversation[-1]['content'].strip()

def merge_lists_without_duplicate(a: list, b: list):
    result = []
    for item in a:
        if item not in result:
            result.append(item)
    for item in b:
        if item not in result:
            result.append(item)
    return result

def fetch_image_description():
    global context_description
    object_list = []
    label_list = []
    while True:
        temp_object_list = []
        temp_label_list = []
        current_time = time.time()
        for i in range(3):
            current_time = time.time()
            print("fetched image")
            with io.open("./hackathon_environment.jpg", 'rb') as image_file:
                content = image_file.read()
            image = vision.Image(content=content)
            features = [vision.Feature.Type.OBJECT_LOCALIZATION, vision.Feature.Type.LABEL_DETECTION]
            response = analyze_image_from_uri(image, features)
            print("fetched image response")
            temp_object_list = merge_lists_without_duplicate(get_unique_objects_list(response), temp_object_list)
            temp_label_list = merge_lists_without_duplicate(get_unique_labels_list(response), temp_label_list)
            time.sleep(max(0, 5 - (time.time() - current_time)))
        if len(object_list) == 0 or len(set(object_list) & set(temp_object_list)) / len(object_list) < 0.4:
            print("context changed")
            object_list = temp_object_list
            label_list = temp_label_list
            contains_computer = False
            for item in object_list + label_list:
                if "computer" in item or "Computer" in item:
                    contains_computer = True
                    break
            context_data_lock.acquire()
            context_description = get_objects_description(object_list) + "\n\n" + get_labels_description(label_list)
            if contains_computer:
                context_description = context_description + "\n\n" + get_app_activity()
            context_data_condition.notify()
            context_data_lock.release()
            print("released")

def start_fetching_images():
    thread = threading.Thread(target=fetch_image_description)
    thread.setDaemon(True)
    thread.start()

def main():
    global context_description
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './hackathon-key.json'
    start_fetching_app_names()
    start_fetching_images()
    prompt = "Given the user's activity log below, summarize the user's major task in less than 10 words." + \
         " Notice that the user might have small distractions during the process." + " Please remove all prefixes like \"Task:\", subjects, and verbs in your response."
    while True:
        context_data_lock.acquire()
        context_data_condition.wait()
        print("got here")
        text = "--- Role ---\nStudent" + "\n\n" + context_description
        context_data_lock.release()
        prompt = prompt + "\n\n" + text
        print(prompt)
        response = ask_gpt(prompt)
        print(response[:-1])

if __name__ == "__main__":
    main()

