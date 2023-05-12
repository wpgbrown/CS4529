# CS4529

## Running the code

Those who want to run the code should use linux. No guarantees are provided that the code will work on other platforms.

You must install the latest version of python which can downloaded at [python.org](https://www.python.org/downloads/).

The libraries in the file [requirements.txt](requirements.txt) must be installed which can be done by running ```pip install -r requirements.txt``` in the console with the working directory as the root directory of this project.

You must also have credentials to use the Gerrit REST API on MediaWiki's Gerrit instance. To do this you need to create a file named secrets.py. You can copy the file named secrets.example.py to do this.

Implement the abstract methods provided in the SecretsInterface class by specifying the valid
secrets needed. This will allow the code to query APIs that require authentication.

If evaluating the code with the training and testing data set it is possible not to need the API credentials, but you will need all the data collected included in your copy of this repository to ensure that the agent works.