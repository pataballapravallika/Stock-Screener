import numpy as np
from scipy.signal import find_peaks


def swing_points(df, distance=10):

    highs, _ = find_peaks(
        df["High"].values,
        distance=distance
    )

    lows, _ = find_peaks(
        -df["Low"].values,
        distance=distance
    )

    df["SwingHigh"] = False
    df["SwingLow"] = False

    df.loc[df.index[highs], "SwingHigh"] = True
    df.loc[df.index[lows], "SwingLow"] = True

    return df


def double_top(df, tolerance=0.03):

    df["DoubleTop"] = False

    peaks = df[df["SwingHigh"]]

    if len(peaks) < 2:
        return df

    for i in range(1, len(peaks)):

        p1 = peaks.iloc[i - 1]["High"]
        p2 = peaks.iloc[i]["High"]

        difference = abs(p1 - p2) / p1

        if difference <= tolerance:
            idx = peaks.index[i]
            df.loc[idx, "DoubleTop"] = True

    return df


def head_shoulders(df, tolerance=0.05):

    df["HeadShoulders"] = False

    peaks = df[df["SwingHigh"]]

    if len(peaks) < 3:
        return df

    for i in range(2, len(peaks)):

        left = peaks.iloc[i - 2]["High"]
        head = peaks.iloc[i - 1]["High"]
        right = peaks.iloc[i]["High"]

        shoulders_similar = (
            abs(left - right) / left
        ) <= tolerance

        if head > left and head > right and shoulders_similar:

            df.loc[
                peaks.index[i],
                "HeadShoulders"
            ] = True

    return df