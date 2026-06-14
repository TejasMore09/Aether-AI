import pandas as pd

def load_and_clean_data(path):
    df = pd.read_csv("data/raw/employee_data.csv")

    # Convert Hire_Date to datetime
    df["Hire_Date"] = pd.to_datetime(df["Hire_Date"])

    # Drop ID column
    df = df.drop(columns=["Employee_ID"])

    # Encode target
    df["Resigned"] = df["Resigned"].astype(int)

    return df


if __name__ == "__main__":
    df = load_and_clean_data("data/raw/employee_data.csv")
    print(df.head())
    print(df.info())
