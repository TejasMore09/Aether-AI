import pandas as pd

def create_time_windows(df):

    df = df.sort_values("Hire_Date")

    df["year"] = df["Hire_Date"].dt.year

    w1 = df[(df["year"] >= 2015) & (df["year"] <= 2017)]
    w2 = df[(df["year"] >= 2018) & (df["year"] <= 2019)]
    w3 = df[(df["year"] >= 2020) & (df["year"] <= 2021)]
    w4 = df[(df["year"] >= 2022) & (df["year"] <= 2023)]

    return w1, w2, w3, w4


if __name__ == "__main__":
    from preprocessing import load_and_clean_data

    df = load_and_clean_data("data/raw/employee_data.csv")
    w1, w2, w3, w4 = create_time_windows(df)

    print(len(w1), len(w2), len(w3), len(w4))

w1.to_csv("data/processed/window1.csv", index=False)
w2.to_csv("data/processed/window2.csv", index=False)
w3.to_csv("data/processed/window3.csv", index=False)
w4.to_csv("data/processed/window4.csv", index=False)

print("Windows saved to data/processed/")