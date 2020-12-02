# Final Project - Using ML and NBA games to predict winners
# 0 = home team loses; 1 = home team wins
# Brenton Wilder

# Import libraries
import pickle
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import (
    AdaBoostClassifier,
    BaggingClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import accuracy_score, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import BernoulliNB, GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVC, NuSVC
from sklearn.tree import DecisionTreeClassifier, ExtraTreeClassifier
from xgboost import XGBClassifier


def main():

    # Load dataframes and clean
    df = pd.read_csv("./data/games.csv", na_filter=False)
    nan_value = float("NaN")
    df.replace("", nan_value, inplace=True)
    df = df.dropna()
    df.drop_duplicates()
    df.sort_values("GAME_DATE_EST")
    df.set_index("GAME_DATE_EST")
    df.drop(["GAME_STATUS_TEXT", "TEAM_ID_home"], axis=1, inplace=True)

    df_tm = pd.read_csv("./data/teams.csv", na_filter=False)
    df_tm.replace("", nan_value, inplace=True)
    df_tm = df_tm.dropna()

    df_rnk = pd.read_csv("./data/ranking.csv", na_filter=False)
    df_rnk.replace("", nan_value, inplace=True)
    df_rnk = df_rnk.dropna()
    df_rnk.sort_values("STANDINGSDATE")
    df_rnk.set_index("STANDINGSDATE")

    # Begin Feature Engineering (1-6 from data)
    # Feature 7: Home Team arena capacity
    # Feature 8: Year Home Team was founded
    # Feature 9: Conference of Home Team, West=0 and East=1
    homID = "HOME_TEAM_ID"
    df_tm = df_tm.rename(columns={"TEAM_ID": "HOME_TEAM_ID"})
    df = pd.merge(
        df,
        df_tm[[homID, "ARENACAPACITY", "YEARFOUNDED", "CONFERENCE"]],
        on="HOME_TEAM_ID",
        how="left",
    )
    df = df.rename(
        columns={
            "YEARFOUNDED": "YEARFOUNDED_homeTeam",
            "CONFERENCE": "CONFERENCE_homeTeam",
            "ARENACAPACITY": "ARENACAPACITY_homeTeam",
        }
    )

    # Feature 10: Away Team arena capacity
    # Feature 11: Year Away Team was founded
    # Feature 12: Conference of Away Team, West=0 and East=1
    visID = "VISITOR_TEAM_ID"
    df_tm = df_tm.rename(columns={"HOME_TEAM_ID": "VISITOR_TEAM_ID"})
    df = pd.merge(
        df,
        df_tm[[visID, "ARENACAPACITY", "YEARFOUNDED", "CONFERENCE"]],
        on="VISITOR_TEAM_ID",
        how="left",
    )
    df = df.rename(
        columns={
            "YEARFOUNDED": "YEARFOUNDED_awayTeam",
            "CONFERENCE": "CONFERENCE_awayTeam",
            "ARENACAPACITY": "ARENACAPACITY_awayTeam",
        }
    )

    # Feature 13: Current win percentage for Home Team
    # Feature 14: Games played so far for Home Team (0-82)
    # Feature 15: Current W for Home Team
    # Feature 16: Current L for Home Team
    df_rnk.drop(
        [
            "LEAGUE_ID",
            "SEASON_ID",
            "CONFERENCE",
            "TEAM",
            "HOME_RECORD",
            "ROAD_RECORD",
        ],
        axis=1,
        inplace=True,
    )
    df = pd.merge_asof(
        df,
        df_rnk.add_suffix("_homeTeam"),
        left_index=True,
        right_index=True,
        left_by="HOME_TEAM_ID",
        right_by="TEAM_ID" + "_homeTeam",
        allow_exact_matches=False,
    )
    df = df.dropna()
    homStd = "STANDINGSDATE_homeTeam"
    df.drop(["TEAM_ID_homeTeam", homStd], axis=1, inplace=True)

    # Feature 17: Current win percentage for Away Team
    # Feature 18: Games played so far for Away Team (0-82)
    # Feature 19: Current W for Away Team
    # Feature 20: Current L for Away Team
    df = pd.merge_asof(
        df,
        df_rnk.add_suffix("_awayTeam"),
        left_index=True,
        right_index=True,
        left_by="VISITOR_TEAM_ID",
        right_by="TEAM_ID" + "_awayTeam",
        allow_exact_matches=False,
    )
    df = df.dropna()
    visStd = "STANDINGSDATE_awayTeam"
    df.drop(["TEAM_ID_awayTeam", visStd], axis=1, inplace=True)

    # Feature 21: Day of the week game is on (0-6)
    df["WEEKDAY"] = df["GAME_DATE_EST"].apply(
        lambda x: (
            datetime.fromordinal(datetime(1900, 1, 1).toordinal() + x - 2)
        ).weekday()
    )

    # Feature 22: Weekend game?  (1=True,0=False)
    df["WEEKEND_GAME"] = df["WEEKDAY"].apply(lambda x: 0 if x < 5 else 1)

    # Feature 23: Month number game is on (1-12)
    df["MONTH_NUM"] = df["GAME_DATE_EST"].apply(
        lambda x: (
            datetime.fromordinal(datetime(1900, 1, 1).toordinal() + x - 2)
        ).strftime("%m")
    )

    # Feature 24: Is this a playoff game (April-June)? (1=True,0=False)
    df = df.astype(float)
    df["PLAYOFF_GAME"] = df["MONTH_NUM"].apply(
        lambda x: 1 if (x <= 6 and x >= 4) else 0
    )

    # Feature 25: Home Team long-term averages PPG (2004-2020)
    # Feature 26: '' '' FG percent
    # Feature 27: '' '' FT percent
    # Feature 28: '' '' FG3 percent
    # Feature 29: '' '' AST per game
    # Feature 30: '' '' REB per game

    table = (
        pd.pivot_table(df, values="PTS_home", index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"PTS_home": "HIST_PPG_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    fghom = "FG_PCT_home"
    table = (
        pd.pivot_table(df, values=fghom, index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FG_PCT_home": "HIST_FGpercent_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    fthom = "FT_PCT_home"
    table = (
        pd.pivot_table(df, values=fthom, index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FT_PCT_home": "HIST_FTpercent_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    fg3hom = "FG3_PCT_home"
    table = (
        pd.pivot_table(df, values=fg3hom, index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FG3_PCT_home": "HIST_FG3percent_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    table = (
        pd.pivot_table(df, values="AST_home", index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"AST_home": "HIST_APG_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    table = (
        pd.pivot_table(df, values="REB_home", index=[homID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"REB_home": "HIST_REB_homeTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="HOME_TEAM_ID",
        how="left",
    )
    # Feature 31: Away Team long-term averages PPG (2004-2020)
    # Feature 32: '' '' FG percent
    # Feature 33: '' '' FT percent
    # Feature 34: '' '' FG3 percent
    # Feature 35: '' '' AST per game
    # Feature 36: '' '' REB per game
    awayID = "TEAM_ID_away"
    ptawy = "PTS_away"
    table = (
        pd.pivot_table(df, values=ptawy, index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"PTS_away": "HIST_PPG_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )
    fgawy = "FG_PCT_away"
    table = (
        pd.pivot_table(df, values=fgawy, index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FG_PCT_away": "HIST_FGpercent_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )
    ftawy = "FT_PCT_away"
    table = (
        pd.pivot_table(df, values=ftawy, index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FT_PCT_away": "HIST_FTpercent_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )
    f3awy = "FG3_PCT_away"
    table = (
        pd.pivot_table(df, values=f3awy, index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"FG3_PCT_away": "HIST_FG3percent_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )
    table = (
        pd.pivot_table(df, values="AST_away", index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"AST_away": "HIST_APG_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )
    table = (
        pd.pivot_table(df, values="REB_away", index=[awayID], aggfunc=np.mean)
        .reset_index()
        .rename(columns={"REB_away": "HIST_REB_awayTeam"})
    )
    df = pd.merge(
        df,
        table,
        on="TEAM_ID_away",
        how="left",
    )

    # Feature 37: Difference long-term averages PPG (2004-2020)
    # Home Team minus Away Team
    df["DIFF_HIST_PPG"] = df["HIST_PPG_homeTeam"] - df["HIST_PPG_awayTeam"]

    # Feature 38: Difference long-term FG percent
    sactown = "HIST_FGpercent_homeTeam"
    df["DIFF_HIST_FG"] = df[sactown] - df["HIST_FGpercent_awayTeam"]

    # Feature 39: Difference long-term FT percent
    kings = "HIST_FTpercent_homeTeam"
    df["DIFF_HIST_FT"] = df[kings] - df["HIST_FTpercent_awayTeam"]

    # Feature 40: Difference long-term FG3 percent
    df["DIFF_HIST_FG3"] = (
        df["HIST_FG3percent_homeTeam"] - df["HIST_FG3percent_awayTeam"]
    )

    # Feature 41: Difference long-term Assists per game
    df["DIFF_HIST_APG"] = df["HIST_APG_homeTeam"] - df["HIST_APG_awayTeam"]

    # Feature 42: Difference long-term Rebounds per game
    df["DIFF_HIST_REB"] = df["HIST_REB_homeTeam"] - df["HIST_REB_awayTeam"]

    # Feature 43:

    # Try all of the models
    # Drop all stats from the actual game (target leakage)
    y = df["HOME_TEAM_WINS"]
    X = df.drop(
        columns=[
            "HOME_TEAM_WINS",
            "PTS_home",
            "FG_PCT_home",
            "FT_PCT_home",
            "FG3_PCT_home",
            "AST_home",
            "REB_home",
            "PTS_away",
            "FG_PCT_away",
            "FT_PCT_away",
            "FG3_PCT_away",
            "AST_away",
            "REB_away",
        ],
        axis=1,
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=2424
    )
    classifiers = [
        ExtraTreeClassifier(random_state=2408),
        DecisionTreeClassifier(random_state=2408),
        MLPClassifier(),
        KNeighborsClassifier(),
        AdaBoostClassifier(),
        GradientBoostingClassifier(),
        BaggingClassifier(),
        RandomForestClassifier(random_state=2408),
        BernoulliNB(),
        GaussianNB(),
        LinearDiscriminantAnalysis(),
        LogisticRegression(),
        LogisticRegressionCV(),
        NuSVC(probability=True),
        SVC(probability=True),
        XGBClassifier(),
    ]
    result_table = pd.DataFrame(columns=["classifiers", "fpr", "tpr", "auc"])

    # Run each model and append to a table
    for cls in classifiers:
        model = cls.fit(X_train, y_train)
        yproba = model.predict_proba(X_test)[::, 1]
        fpr, tpr, _ = roc_curve(y_test, yproba)
        auc = roc_auc_score(y_test, yproba)
        result_table = result_table.append(
            {
                "Classifiers": cls.__class__.__name__,
                "fpr": fpr,
                "tpr": tpr,
                "AUC": auc,
            },
            ignore_index=True,
        )

    # Plot bar graph comparing ROC/AUC
    fig = px.bar(result_table, x="Classifiers", y="AUC")
    fig.update_traces(
        marker_color="rgb(158,202,225)",
        marker_line_color="rgb(8,48,107)",
        marker_line_width=1.5,
        opacity=0.9,
    )
    fig.update_layout(
        paper_bgcolor="rgb(0,0,0,0)",
        title="AUC values from ROC curve",
        font=dict(family="Times New Roman", size=20, color="black"),
    )
    fig.show()

    # Select best model
    # For this study, we used AUC of ROC curve
    # as the performance metric to select optimal model
    column = result_table["AUC"]
    max_index = column.idxmax()
    final = result_table.loc[max_index, "Classifiers"]

    # Show feature importance for best model
    final = eval(final)()
    final.fit(X_train, y_train)
    y_pred = final.predict(X_test)
    y_score = final.predict_proba(X_test)[::, 1]
    print("_________Final Model_________")
    print("Accuracy:", accuracy_score(y_test, y_pred))
    imp = pd.Series(final.feature_importances_, index=X.columns).sort_values(
        ascending=False
    )
    print("FEATURE IMPORTANCE:")
    print(imp)

    # Plot the ROC curve for final model
    fpr2, tpr2, thresholds = roc_curve(y_test, y_score)
    auc2 = roc_auc_score(y_test, y_score)
    fig2 = px.area(
        x=fpr2,
        y=tpr2,
        title=f"ROC Curve for Final Model (AUC={auc2})",
        labels=dict(x="False Positive Rate", y="True Positive Rate"),
        width=700,
        height=500,
    )
    fig2.add_shape(type="line", line=dict(dash="dash"), x0=0, x1=1, y0=0, y1=1)
    fig2.update_layout(
        paper_bgcolor="rgb(0,0,0,0)",
        font=dict(family="Times New Roman", size=20, color="black"),
    )
    fig2.update_yaxes(scaleanchor="x", scaleratio=1)
    fig2.update_xaxes(constrain="domain")
    fig2.show()

    # Plot the importance chart for final model
    importances = final.feature_importances_
    indices = np.argsort(importances)[::-1]
    fig3 = go.Figure()
    fig3.add_trace(
        go.Bar(
            x=indices,
            y=importances,
        )
    )
    fig3.update_layout(
        paper_bgcolor="rgb(0,0,0,0)",
        font=dict(family="Times New Roman", size=20, color="black"),
        xaxis_title="Feature #",
        yaxis_title="Feature Importance",
    )
    fig3.show()

    # Run Exhaustive Feature Selector (brute force)
    # efs1 = EFS(
    #    final,
    #    min_features=1,
    #    max_features=1,
    #    scoring="roc_auc",
    #    print_progress=True,
    #    cv=5,
    # )

    # efs1 = efs1.fit(X, y)
    # df_bf = pd.DataFrame.from_dict(efs1.get_metric_dict()).T
    # df_bf.sort_values("avg_score", inplace=True, ascending=False)

    # Export brute force spreadsheet
    # df_bf.to_csv("brute_force.csv")

    # Export model to pickle file
    with open("./final_model.pkl", "wb") as model_pkl:
        pickle.dump(final, model_pkl)


if __name__ == "__main__":
    sys.exit(main())
