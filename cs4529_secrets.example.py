"""
Contains secrets needed that are user-specific and should never be uploaded to github
"""
from secrets_interface import SecretsInterface

class Secrets(SecretsInterface):
    def gerrit_http_credentials(self):
        return "test user", "test password"