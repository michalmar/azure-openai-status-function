import azure.functions as func
import logging
import subprocess
import json
import os
import json
from openai import AzureOpenAI
import time
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobClient, ContentSettings


load_dotenv()


SYSTEM_DEFAULT_PROMPT = "Assistant is a large language model trained by OpenAI."
messages = [
                {"role": "system", "content": SYSTEM_DEFAULT_PROMPT},

            ]

messages.append({"role": "user", "content": "How are you?"})

AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING', None)
AZURE_STORAGE_CONTAINER_NAME_IMAGES = os.getenv('AZURE_STORAGE_CONTAINER_NAME_IMAGES', None)
AZURE_STORAGE_CONTAINER_NAME_DOCS = os.getenv('AZURE_STORAGE_CONTAINER_NAME_DOCS', None)

# DIR_IN = os.path.join("data","in")
# DIR_OUT = os.path.join("data","out")
# DIR_OUT_IMAGES = os.path.join("data","out", "images")

def get_services(verbose=False):
    # Command to call the command-line program
    command = "az cognitiveservices account list -g rg-ai-openai"

    # Execute the command and capture the output
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()

    # Decode the output to a string, then load it into a Python variable as JSON
    if process.returncode == 0:
        json_data = json.loads(output.decode('utf-8'))
    else:
        print("Error executing command:", error.decode('utf-8'))
        json_data = None

    # Now json_data contains the list of JSONs
    # We can now extract the details of the cognitive service account
    # For example, the endpoint and the key


    # endpoint = json_data[0]["properties"]["endpoint"]
    # name = json_data[0]["name"]
    # location = json_data[0]["location"]

    services = {}

    for item in json_data:    

        endpoint = item["properties"]["endpoint"]
        name = item["name"]
        location = item["location"]
        kind = item["kind"]

        services[name] = {
            "name": name,
            "endpoint": endpoint,
            "location": location,
            "kind": kind
        }

    for openai_name, _ in services.items():
        # print(key, value)
        command = "az cognitiveservices account keys list -g rg-ai-openai -n " + openai_name
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = process.communicate()

        if process.returncode == 0:
            json_data = json.loads(output.decode('utf-8'))
        else:
            print("Error executing command:", error.decode('utf-8'))
            json_data = None

        key = json_data["key1"]

        services[openai_name]["key"] = key
    
    print(f"Found {len(services)} services.")
    if verbose:
        for key, value in services.items():
            print(key)
            print(value)
    return services

def get_deployments(name):


    command = f"az cognitiveservices account deployment list --name {name} --resource-group rg-ai-openai"

    # Execute the command and capture the output
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()

    # Decode the output to a string, then load it into a Python variable as JSON
    if process.returncode == 0:
        json_data = json.loads(output.decode('utf-8'))
    else:
        print("Error executing command:", error.decode('utf-8'))
        json_data = None

    # json_data = get_deployments("openaimma-swedencentral")
    deployments = {}
    deployments[name] = []
    for item in json_data:  
        # print(item["name"], item["properties"]["capabilities"]["embeddings"]) 

        if "embeddings" in item["properties"]["capabilities"]:
            # print(item["name"], item["properties"]["capabilities"]["embeddings"])
            # deployments[item["name"]] = "embeddings"
            deployments[name].append({"id": item["name"], "type": "embeddings", "model": item["properties"]["model"]["name"], "version": item["properties"]["model"]["version"]})

        elif "chatCompletion" in item["properties"]["capabilities"]:
            # print(item["name"], item["properties"]["capabilities"]["chatCompletion"])
            # deployments[item["name"]] = "chatCompletion"
            deployments[name].append({"id": item["name"], "type": "chatCompletion", "model": item["properties"]["model"]["name"], "version": item["properties"]["model"]["version"]})
        else:
            print(item["name"], "No capabilities")
            # deployments[item["name"]] = "N/A"
            deployments[name].append({"id": item["name"], "type": "N/A", "model": item["properties"]["model"]["name"], "version": item["properties"]["model"]["version"]})

    
    return deployments

def get_chat_deployments(deployments, service_name, model_family = None):
    chat_deployments = []
    for deployment in deployments[service_name]:
        if deployment["type"] == "chatCompletion" and (model_family is None or deployment["model"] == model_family):
            # return deployment["id"]
            chat_deployments.append(deployment)

    return chat_deployments

def test_services(services, model_family = "gpt-4", verbose=False):

    call_log = []
    for service_name, value in services.items():
        # print(service_name, details)
        if verbose:
            print(f"Running tests for service {service_name}")

        deployments = get_deployments(service_name)
        
        if verbose:
            print(f"Found {len(deployments[service_name])} deployments for service {service_name}")

        if len(deployments[service_name]) == 0:
            print(f"No deployments found for service {service_name}.")
            continue

        chat_deployments = get_chat_deployments(deployments, service_name, model_family)

        if len(chat_deployments) == 0:
            if verbose:
                print(f"No deployment found for model family {model_family}")
            continue
        
        for deplyment_dict in chat_deployments:
            print(f"Testing deployment {deplyment_dict['id']} version {deplyment_dict['version']} for service {service_name}") 
            deployment = deplyment_dict["id"]

            client = AzureOpenAI(
                api_version="2023-05-15",
                azure_endpoint=value["endpoint"],
                api_key=value["key"],
            ) 

            # Start time
            start_time = time.time()

            # API call
            response = client.chat.completions.create(
                # model="gpt-35-turbo",  # model = "deployment_name"
                model=deployment,
                messages=messages,
                temperature=0.7,
                max_tokens=800,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stop=None
            )

            # messages.append({"role": "assistant", "content": response.choices[0].message.content}) 

            # End time
            end_time = time.time()

            # Calculate duration
            duration = end_time - start_time
            # print(f"API call duration: {duration} seconds")

            # Get the length of the request and response
            _len = 0
            for m in messages:
                _len = _len + len(m["content"])

            req_resp_len = _len + len(response.choices[0].message.content)

            call_log.append({
                "service": service_name,
                "deployment": deployment,
                "version": deplyment_dict['version'],
                "model_family": model_family,
                "start_time": start_time,
                "duration": duration,
                "length": req_resp_len
            })

            response_message = response.choices[0].message.content


            # response.choices[0].message.content


    return call_log

# model_family = "gpt-35-turbo"
def run_test(model_family = "gpt-4", filter_to_regions = []):
    print("Preparing to test services...")
    services = get_services(verbose=True)

    if len(filter_to_regions)>0:
        regions = filter_to_regions

        # Filter services to only include those with location "east"
        services_filtered = {name: details for name, details in services.items() if details["location"] in regions}
        print(f"Found {len(services_filtered)} services in the regions {regions}")
        # for key, value in services_filtered.items():
        #     print(key, value)

        services = services_filtered

    print(f"Testing all services for model family {model_family}")
    # call_log = test_services(services_filtered)
    call_log = test_services(services, model_family)

    # create pandas dataframe from call_log
    df = pd.DataFrame(call_log)

    # convert start_time to datetime
    df["start_time"] = pd.to_datetime(df["start_time"], unit='s')

    # df.dtypes
    # current date and time to string YYYY-MM-DD HH-MM-SS
    current_time = time.strftime("%Y%m%d-%H%M%S")
    df.to_csv(f"call_log{current_time}.csv", index=False)

    # Convert DataFrame to CSV string
    csv_data = df.to_csv(index=False)

    storage_url = write_doc_on_blob_storage(csv_data, f"call_log{current_time}.csv")

    print(f"Call log saved to {storage_url}")

    # get service_name name where duration max duration is
    max_duration = df["duration"].max()
    max_duration_service = df[df["duration"] == max_duration]["service"].values[0]
    print(f"Max duration {max_duration} for service {max_duration_service}")

    # get service_name name where duration is minimum
    min_duration = df["duration"].min()
    min_duration_service = df[df["duration"] == min_duration]["service"].values[0]
    print(f"Min duration {min_duration} for service {min_duration_service}")

    # get average duration
    avg_duration = df["duration"].mean()
    print(f"Average duration {avg_duration}")



def write_doc_on_blob_storage(doc, filename):

    document_data = doc
    container_name = AZURE_STORAGE_CONTAINER_NAME_DOCS
    blob_name = filename
    if AZURE_STORAGE_CONNECTION_STRING and container_name:
        # Create full Blob URL
        x = AZURE_STORAGE_CONNECTION_STRING.split(';')
        doc_url = f"{x[0].split('=')[1]}://{x[1].split('=')[1]}.{x[3].split('=')[1]}/{container_name}/{blob_name}"
        # Upload data on Blob
        blob_client = BlobClient.from_connection_string(conn_str=AZURE_STORAGE_CONNECTION_STRING, container_name=container_name, blob_name=blob_name)
        content_settings = ContentSettings(content_type='text/markdown')
        blob_client.upload_blob(document_data, content_settings=content_settings, overwrite=True)
        return doc_url


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="openai_status_run")
def openai_status_run(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # name = req.params.get('name')
    # if not name:
    #     try:
    #         req_body = req.get_json()
    #     except ValueError:
    #         pass
    #     else:
    #         name = req_body.get('name')
    

    start_time = time.time()
    run_test(model_family="gpt-4")
    end_time = time.time()
    duration1 = end_time - start_time

    start_time = time.time()
    run_test(model_family="gpt-35-turbo")
    end_time = time.time()
    duration2 = end_time - start_time
    duration_all = duration1 + duration2
    

    return func.HttpResponse(f"All tests run succesfully: Test for gpt-4 took {duration1} seconds, Test for gpt-35-turbo took {duration2} seconds. Total duration {duration_all} seconds.")

    # if name:
    #     return func.HttpResponse(f"Helloss!!!, {name}. This HTTP triggered function executed successfully.")
    # else:
    #     return func.HttpResponse(
    #          "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
    #          status_code=200
    #     )

@app.timer_trigger(schedule="0 5 * * * *", arg_name="myTimer", run_on_startup=True,
              use_monitor=False) 
def openai_status_run_scheduled(myTimer: func.TimerRequest) -> None:
    
    if myTimer.past_due:
        logging.info('The timer is past due!')

    start_time = time.time()
    run_test(model_family="gpt-4")
    end_time = time.time()
    duration1 = end_time - start_time

    start_time = time.time()
    run_test(model_family="gpt-35-turbo")
    end_time = time.time()
    duration2 = end_time - start_time
    duration_all = duration1 + duration2
    logging.info('All tests run succesfully: Test for gpt-4 took {duration1} seconds, Test for gpt-35-turbo took {duration2} seconds. Total duration {duration_all} seconds.')