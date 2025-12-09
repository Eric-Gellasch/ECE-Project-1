import os # used for getting files and tracing file paths
import glob # going to let us pull groups of files with things like the .csv

import numpy as np # simple numerics
import pandas as pd # This is how the file will read csvs and make them into readable data


from xgboost import XGBClassifier # using from...import makes writing cleaner XGBClasifer(...) instead of xgboost.XGBClasifier
from sklearn.model_selection import train_test_split # splits data into training and tesitng parts
from sklearn.preprocessing import LabelEncoder # allows you to call strings like Eric_G
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.metrics import accuracy_score, roc_auc_score
from joblib import dump

import matplotlib.pyplot as plt

## PULLING ALL OF THE DATA INTO THE MODEL

DATA_DIR = "Keystroke_Data"

# pattern to find all the files in the keystrokes data folder
pattern = os.path.join(DATA_DIR,"*_keystrokes.csv")
file_list = glob.glob(pattern)

# creates a loop to read each csv file individually
print("found csv files")
for f in file_list:
    print("",f)

# read each csv and tag with a userID from the filename

dfs = []
for fname in file_list:
    df = pd.read_csv(fname)
    base = os.path.basename(fname)
    user_id = base.replace("_keystrokes.csv","")
    df["user_id"]=user_id # new column with no space id
    dfs.append(df)


full = pd.concat(dfs,ignore_index=True)

print("\nCombined shape:", full.shape)
print("Columns:", list(full.columns))
print("\nHead:")
print(full.head())

## TELLING THE MODEL HOPW TO PROCESS THE ROWS AND COLUMNS

# First we much seperate each row for each user 
def build_attempt_features(events_df: pd.DataFrame) -> pd.DataFrame:

# each row is like a sample for the model to look at 
# only look at lettersw typed looks at the ch column in the data
    char_df = events_df[events_df["ch"]!="-"].copy()

# groups user, attempt, and event all together for each row for each user
    char_df = char_df.sort_values(["user_id","attempt_id","event_idx"])

    feature_rows = []

# This will make the rows look like this:
# {"user_id": "Eric", "attempt_id": 1, "dwell_mean": ..., ...},

    grouped = char_df.groupby(["user_id","attempt_id"])

    for (user_id, attempt_id), group in grouped:
        # For this single attempt, pull arrays of timing values
        dwells = group["dwell_ms"].values
        flights_ud = group["flight_ud_ms"].values
        flights_dd = group["flight_dd_ms"].values
        
        # --- Basic statistics for dwell times ---
        dwell_mean = dwells.mean()
        dwell_std = dwells.std(ddof=0)
        
        # --- Flight times (skip the first since it's weird/zero) ---
        if len(flights_ud) > 1:
            flight_ud_mean = flights_ud[1:].mean()
            flight_ud_std  = flights_ud[1:].std(ddof=0)
        else:
            flight_ud_mean = 0.0
            flight_ud_std  = 0.0
        
        if len(flights_dd) > 1:
            flight_dd_mean = flights_dd[1:].mean()
            flight_dd_std  = flights_dd[1:].std(ddof=0)
        else:
            flight_dd_mean = 0.0
            flight_dd_std  = 0.0
        
        # --- Overall attempt duration ---
        start_time = group["press_rel_ms"].min()
        end_time   = group["release_rel_ms"].max()
        attempt_duration = end_time - start_time
        
        feature_rows.append({
            "user_id": user_id,
            "attempt_id": attempt_id,
            "dwell_mean": dwell_mean,
            "dwell_std": dwell_std,
            "flight_ud_mean": flight_ud_mean,
            "flight_ud_std": flight_ud_std,
            "flight_dd_mean": flight_dd_mean,
            "flight_dd_std": flight_dd_std,
            "attempt_duration": attempt_duration,
        })
    
    features_df = pd.DataFrame(feature_rows)
    return features_df

# Actually build the attempt-level features
attempt_features = build_attempt_features(full)

print("\nAttempt-level feature shape:", attempt_features.shape)
print(attempt_features.head())

# ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

# Now we must prepare the data for the model 

user_counts = attempt_features["user_id"].value_counts()
print(".\nAttempts per user:")
print(user_counts)

# Encode user_id (a string luike Eric_g, Molly) becomes 0,1,2,3...

label_encoder = LabelEncoder()
attempt_features["user_label"] = label_encoder.fit_transform(attempt_features["user_id"])

feature_cols = [
    "dwell_mean",
    "dwell_std",
    "flight_ud_mean",
    "flight_ud_std",
    "flight_dd_mean",
    "flight_dd_std",
    "attempt_duration",
]

# the X represents the input to the model it gives the model dwell mean, dwell_std etc
X = attempt_features[feature_cols].values

# This what I want the model to learn it is the output from the model
y = attempt_features["user_label"].values

X_train,X_test,y_train,y_test = train_test_split(
    X,y,
    test_size = 0.3,
    stratify=y,
    random_state=9
)

# Look at the size of our train and test sets

print("X_train shape:",X_train.shape)
print("X_test shape:",X_test.shape)

# count user number
num_classes = len(np.unique(y))

print("Number of classes(users):",num_classes)

# ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

# CREATING THE MODEL

model = XGBClassifier(
    n_estimators=600,          # number of trees more trees usually better preformance
    max_depth=6,              # how deep each tree can go, higher number cna cause overfitting
    learning_rate=0.03,       # how big each boosting step is smaller ismore cautious
    subsample=1,            # use 80% of rows for each tree 
    colsample_bytree=1,     # use 80% of features for each tree
    objective="multi:softprob" if num_classes > 2 else "binary:logistic",
    eval_metric="mlogloss" if num_classes > 2 else "logloss",
    random_state=9            # for reproducibility of the model itself
)

# training the model

print("\nTrainign XGBoost model...")
model.fit(X_train, y_train)

y_pred = model.predict(X_test)

# now we test the accuracy

test_acc = accuracy_score(y_test, y_pred)
print(f"\nTest accuracy: {test_acc:.3f}")

# gives a probablity distribution of the most likely users
y_proba = model.predict_proba(X_test)

if num_classes > 2:
    # multi-class ROC-AUC (one-vs-rest, macro-averaged)
    test_auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="macro")
else:
    # binary case: use probability of class 1
    test_auc = roc_auc_score(y_test, y_proba[:, 1])

print(f"Test ROC-AUC: {test_auc:.3f}")

# ------------------------------------------------
# Inspect some predictions in terms of user_id
# ------------------------------------------------
# Convert numeric labels back to original user_id strings
true_user_ids = label_encoder.inverse_transform(y_test)
pred_user_ids = label_encoder.inverse_transform(y_pred)

results_df = pd.DataFrame({
    "true_user": true_user_ids,
    "pred_user": pred_user_ids
})

print("\nSample predictions (true vs predicted):")
print(results_df.head(20))

