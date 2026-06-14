import pandas as pd
import joblib
from xgboost import XGBClassifier

from features.build_features import build_features
from adaptation.adaptation_engine import encode

TARGET = "Resigned"


def retrain_model(data_paths, encoders):

    df_list = []

    for path in data_paths:
        df = pd.read_csv(path)
        df = build_features(df)
        df_list.append(df)

    data = pd.concat(df_list)

    X = encode(data, encoders)
    y = data[TARGET]

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )

    model.fit(X, y)

    return model