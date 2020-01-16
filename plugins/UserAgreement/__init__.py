

from . import UserAgreement

def getMetaData():
    return {}

def register(app):
    return {"extension": UserAgreement.UserAgreement(app)}
