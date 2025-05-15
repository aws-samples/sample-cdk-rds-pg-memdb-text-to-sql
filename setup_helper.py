# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

import json
import argparse


def get_stack_outputs():
    try:
        with open("outputs.json", "r", encoding="utf-8") as file:
            outputs = json.load(file)
            app_stack = outputs.get("AppStack", {})
            db_init_stack = outputs.get("DatabaseInitStack", {})
            return {
                "bastion_id": app_stack.get("BastionHostInstanceId"),
                "secret_name": db_init_stack.get("DBSecretArn"),
                "api_key_id_command": app_stack.get("GetApiKeyCommand"),
                "api_endpoint": app_stack.get("ApiEndpoint")
            }
    except FileNotFoundError:
        print("Error: outputs.json not found. Please ensure you have deployed the stack.")
        return None
    except json.JSONDecodeError:
        print("Error: outputs.json is not valid JSON.")
        return None


def setup_bastion():
    outputs = get_stack_outputs()
    if outputs:
        print("\nRun this command to access the bastion host:")
        print(
            f"aws ssm start-session --target {outputs['bastion_id']} --document-name AWS-StartInteractiveCommand --parameters command=\"export SECRET_NAME={outputs['secret_name']} && cd ~ && bash\"")


def setup_streamlit():
    outputs = get_stack_outputs()
    if outputs:
        print("\nFollow these steps to set up Streamlit:")
        print("1. Run this command to get the API key:")
        print(outputs['api_key_id_command'])
        print(
            "\n2. In the streamlit/ directory from the root of the project, create a .streamlit/secrets.toml file with the following content:")
        print("api_key = \"<api-key-from-step-1>\"")
        print(f"api_endpoint = \"{outputs['api_endpoint']}\"")
        print("\n3. Install Streamlit and dependencies:")
        print("python3 -m pip install streamlit requests pandas")
        print("\n4. Run the Streamlit app:")
        print("cd streamlit && streamlit run app.py")


def main():
    parser = argparse.ArgumentParser(description="Setup helper for bastion host and Streamlit app")
    parser.add_argument("action", choices=["bastion", "streamlit"], help="Choose between bastion and streamlit setup")
    args = parser.parse_args()

    if args.action == "bastion":
        setup_bastion()
    elif args.action == "streamlit":
        setup_streamlit()


if __name__ == "__main__":
    main()
