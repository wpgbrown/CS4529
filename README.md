# CS4529: Automatic code reviewer recommendations in the open-source project MediaWiki

This repository contains the code written by William Brown for his CS4529 project. If you are viewing a downloaded copy of this repository, the repository is located on GitHub at https://github.com/wpgbrown/CS4529.

## Running the code

Those who want to run the code should use linux. No guarantees are provided that the code will work on other platforms.

You must install python version 3.10 which can be downloaded at [python.org](https://www.python.org/downloads/). Versions below 3.10 will not work due to the use of the "match case" statement in the code.

The libraries in the file [requirements.txt](requirements.txt) must be installed which can be done by running ```pip install -r requirements.txt``` in the console with the working directory as the root directory of this project.

You must also have credentials to use the Gerrit REST API on MediaWiki's Gerrit instance to get recommendations using Change-IDs. To do this you need to create a file named secrets.py. You can copy the file named secrets.example.py to do this.

Implement the abstract methods provided in the SecretsInterface class by specifying the valid secrets needed which can be generated if you have an account at [the MediaWiki Gerrit system](https://gerrit.wikimedia.org/r/settings/#HTTPCredentials). This will allow the code to query APIs that require authentication.

If evaluating the code with the training and testing data set it is possible not to require the need to query the Gerrit REST API and therefore not need these credentials, but you will need all the data collected included in your copy of this repository to ensure that the agent works.
