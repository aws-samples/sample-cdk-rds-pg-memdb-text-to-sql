# Build an AI-powered text-to-SQL chatbot using Amazon Bedrock, Amazon MemoryDB, and Amazon RDS

To manually create a virtualenv on macOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

## Prerequisites
The following are needed in order to proceed with this post:

* An [AWS account](https://aws.amazon.com/).
* A [Git client](https://git-scm.com/downloads) to clone the source code provided.
* [Docker](https://www.docker.com/) installed and running on the local host or laptop.
* [Install AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html)
* The [AWS Command Line Interface (AWS CLI)](https://aws.amazon.com/cli/).
* The AWS Systems Manager [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
* [Amazon Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) enabled for Anthropic Claude 3.5 Sonnet and Amazon Titan Embeddings G1 – Text in the us-west-2 Region.
* Python 3.121 or higher with the pip package manager.
* [500,000+ US Homes Data (For Sale Properties)](https://www.kaggle.com/datasets/polartech/500000-us-homes-data-for-sale-properties)
  * License – [CC0: Public Domain](https://creativecommons.org/publicdomain/zero/1.0/)

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

The dependencies for the text-to-SQL code solution, and custom resource to initialize the database, include their respective requirements.txt file that are installed as part of the CDK deployment.

# Usage
## Download the dataset and upload to Amazon S3

1. Navigate to the [500,000+ US Homes Data dataset](https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset), and download the dataset to your local machine.
2. Unzip the `archive.zip` file, which will expand into a file called `600k US Housing Properties.csv`.
3. Upload this file to an Amazon Simple Storage Service (Amazon S3) bucket of your choice in the AWS account where you'll be deploying the AWS Cloud Development Kit (AWS CDK) solution. Replace `<bucket-name>` with the bucket in your account.
```
aws s3 cp "./600K US Housing Properties.csv" s3://<bucket-name>/
```

## Deploy the solution

1. Clone the repository from GitHub:
```
git clone https://github.com/aws-samples/sample-cdk-rds-pg-memdb-text-to-sql 
cd sample-cdk-rds-pg-memdb-text-to-sql/
```

2. Deploy the CDK application and specify the S3 bucket name used in the previous section as a parameter. It will take about 20-30 minutes to deploy the MemoryDB and RDS instances.
```
cdk bootstrap aws://{{account_id}}/{{region}} 
cdk deploy --all --parameters AppStack:S3BucketName=<bucket-name>
```
Note: if you receive an error at this step, please ensure Docker is running on the local host or laptop.

3. Use the `setup_helper.py` script to access the bastion host:
```
python3 setup_helper.py bastion
```
Run the command provided by the script to use Session Manager, a capability of AWS Systems Manager, to access the bastion host. This will also set the `SECRET_NAME` environment variable for the session to configure the RDS database.
4. On the bastion host, install required dependencies:
```
sudo yum install -y postgresql15 python3-pip 
python3 -m pip install "psycopg[binary]>=3.1.12" boto3 pandas numpy
```
5. Copy the artifact file from the S3 bucket used in the previous section (Download the dataset and upload to Amazon S3) to the bastion host:
```
aws s3 cp "s3://<bucket-name>/600K US Housing Properties.csv" .
```
6. On the same bastion host terminal session, create the following Python code by copying and pasting the code into your terminal:
```
cat > ~/load.py << EOF
import os, json, boto3, psycopg, pandas as pd, numpy as np

def get_secret(secret_name: str):
    """Retrieve database connection parameters from AWS Secrets Manager."""
    sm_client = boto3.client("secretsmanager", region_name="us-west-2")
    connector_params = json.loads(sm_client.get_secret_value(SecretId=secret_name)["SecretString"])
    
    required_fields = ["host", "username", "password", "port"]
    missing = [f for f in required_fields if f not in connector_params]
    if missing:
        raise ValueError(f"Required fields not found: {', '.join(missing)}")
    
    return connector_params

def main():
    csv_file = '600K US Housing Properties.csv'
    
    try:
        print("Processing and importing data...")
        connection_params = get_secret(os.environ["SECRET_NAME"])
        conn_string = f"host={connection_params['host']} port={connection_params['port']} dbname=postgres user={connection_params['username']} password={connection_params['password']}"
        
        # Column names for the COPY statement - defined as a list for safety
        columns = ['property_url', 'property_id', 'address', 'street_name', 'apartment', 'city', 'state', 'latitude', 
                  'longitude', 'postcode', 'price', 'bedroom_number', 'bathroom_number', 'price_per_unit', 'living_space', 
                  'land_space', 'land_space_unit', 'broker_id', 'property_type', 'property_status', 'year_build', 
                  'total_num_units', 'listing_age', 'RunDate', 'agency_name', 'agent_name', 'agent_phone', 'is_owned_by_zillow']

        
        # Connect to database
        with psycopg.connect(conn_string) as conn:
            # Process and import data in chunks
            chunksize = 1000
            total_imported = 0

            # Prepare the INSERT statement with placeholders
            placeholders = ", ".join(["%s"] * len(columns))
            insert_query = f"INSERT INTO us_housing_properties ({', '.join(columns)}) VALUES ({placeholders})"

            for chunk in pd.read_csv(csv_file, chunksize=chunksize):
                # Replace negative values with None
                numeric_cols = chunk.select_dtypes(include=['float64', 'int64']).columns
                chunk[numeric_cols] = chunk[numeric_cols].apply(lambda x: x.mask(x < 0, None))

                # Replace null or empty values with None
                chunk = chunk.replace({np.nan: None, '': None})
                # Create a list of tuples from the DataFrame chunk
                tuples = [tuple(x) for x in chunk.to_numpy()]

                
                # Use executemany for batch insertion
                with conn.cursor() as cur:
                    cur.executemany(insert_query, tuples)
                    conn.commit()
                
                total_imported += len(chunk)
                print(f"Imported {total_imported} rows...")
            
            print(f"Successfully imported {total_imported} rows into database.")

    except Exception as error:
        print(f"Error: {error}")
        raise

if __name__ == "__main__":
    main()
EOF
```
8. Run the Python code to input data into the RDS instance from the spreadsheet. If you receive an error, double check that you set the correct SECRET_NAME as an environment variable in step 4.
```
python3 load.py
```
9. Once the script completes, navigate to the AWS Lambda console from your browser - https://us-west-2.console.aws.amazon.com/lambda/home?region=us-west-2#/functions
10. Search for the function named [`DataIndexerStack-DataIndexerFunction`](https://us-west-2.console.aws.amazon.com/lambda/home?region=us-west-2#/functions/DataIndexerStack-DataIndexerFunction?tab=testing)
11. Open the function, and navigate to the Test tab. Click test. This will populate the embeddings table with database schema information.
12. Next, search for the function named [`AppStack-TextToSQLFunction`]()
13. Open the function, and navigate to the Test tab. Edit the Event JSON with the following:
```
{
  "query": "What are the top homes in San Francisco, CA?"
}
```

## Test the text-to-sql chatbot application

To run the Streamlit app, perform the following steps from your local host or laptop. In this section, we will retrieve the API key and capture the API endpoint from the deployed CDK application.

1. Use the `setup_helper.py` script to set up Streamlit:
python3 setup_helper.py streamlit

The output will look similar to the following:
```bash
Follow these steps to set up Streamlit:

1. Run this command to get the API key: 
aws apigateway get-api-key --api-key <api-id> --include-value --query 'value' --output text

2. In the streamlit/ directory from the root of the project, create a .streamlit/secrets.toml file with the following content: 
api_key = "<api-key-from-step-1>" 
api_endpoint = "https://<api-id>.execute-api.us-west-2.amazonaws.com/prod/"

3. Install Streamlit: 
python3 -m pip install streamlit pandas requests

4. Run the Streamlit app: 
streamlit run app.py
```
2. Follow the instructions provided by the script to:
   1. Retrieve the API key 
   2. Create the .streamlit/secrets.toml file 
   3. Install Streamlit 
   4. Run the Streamlit app

3. Step 4 in the above output will run the Streamlit app using `streamlit run app.py`.

Try some of the following questions to see the responses from the solution:
* What are the key factors affecting home prices in 90210?
* What are top properties in San Francisco, CA?
* What are the top homes in WA where avg sq ft is > $700 and sq ft is > 1000?

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
