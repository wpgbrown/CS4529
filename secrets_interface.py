"""
This interface class defines the secrets needed to run the python code in this
repository. Define secrets.py with a class that extends this
"""

from abc import ABCMeta, abstractmethod

class SecretsInterface(metaclass=ABCMeta):

    """
    The HTTP credentials used when collecting data
    from gerrit.

    Returns a tuple with the first item being the
    username and the second being the password.

    :rtype: tuple
    :return: HTTP credentials
    """
    @property
    @abstractmethod
    def gerrit_http_credentials(self) -> tuple:
        pass