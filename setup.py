from setuptools import setup, find_packages

setup(
    name="emailtag",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn==0.24.0",
        "celery==5.4.0",
        "sqlalchemy==2.0.23",
        "psycopg2-binary==2.9.9",
        "openai==1.59.3",
    ],
) 