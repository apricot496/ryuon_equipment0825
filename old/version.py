import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import oauth2client

print("Streamlit ==", st.__version__)
print("Pandas ==", pd.__version__)
print("numpy ==", np.__version__)
print("gspread ==", gspread.__version__)
print("oauth2client ==", oauth2client.__version__)
