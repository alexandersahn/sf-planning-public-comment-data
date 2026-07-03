"""Impute comment polarity for unsigned comments with a classifier trained on
the stenographer's signs.

Trains TF-IDF + logistic regression on the ~55k comments that carry a
stenographer sign (+/-/=) and have comment text; validates with 5-fold CV and
a held-out test set; then predicts signs for unsigned comments with text.
Predictions are written as separate columns (`sign_imputed`, `sign_prob`,
`sign_source`) — the stenographer's `sign` column is never modified.

Writes: data/processed/comments.csv (columns added)
        data/validation/polarity_report.txt
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"

MIN_TEXT = 10          # characters of comment text required
CONF_THRESHOLD = 0.70  # only accept predictions at/above this probability


def clean_text(s):
    s = str(s)
    s = re.sub(r"\[Re:[^\]]*\]", " ", s)   # topic headers carry no tone
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    df = pd.read_csv(OUT / "comments.csv", low_memory=False,
                     keep_default_na=False, na_values=[""])
    df["comment_txt"] = df["comment"].fillna("").map(clean_text)
    has_text = df["comment_txt"].str.len() >= MIN_TEXT

    train = df[df["sign"].isin(["+", "-", "="]) & has_text]
    X, y = train["comment_txt"], train["sign"]

    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced"),
    )

    # honest evaluation before fitting on everything
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.15, random_state=7, stratify=y)
    model.fit(X_tr, y_tr)
    pred_te = model.predict(X_te)
    proba_te = model.predict_proba(X_te).max(axis=1)
    report = classification_report(y_te, pred_te, digits=3)
    cm = confusion_matrix(y_te, pred_te, labels=["+", "-", "="])
    acc = (pred_te == y_te).mean()
    conf_mask = proba_te >= CONF_THRESHOLD
    acc_conf = (pred_te[conf_mask] == y_te.values[conf_mask]).mean()
    cv = cross_val_score(model, X, y, cv=5, scoring="accuracy")

    # final model on all signed data
    model.fit(X, y)

    # predict unsigned comments that have text; role-implied signs (set by
    # assign_roles.py) take precedence and are preserved
    if "sign_source" not in df.columns:
        df["sign_source"] = pd.NA
    if "sign_imputed" not in df.columns:
        df["sign_imputed"] = pd.NA
    role_locked = df["sign_source"] == "role"
    target = df[df["sign"].isna() & has_text & ~role_locked]
    preds = model.predict(target["comment_txt"])
    probs = model.predict_proba(target["comment_txt"]).max(axis=1)

    df.loc[~role_locked, "sign_imputed"] = pd.NA
    df["sign_prob"] = pd.NA
    accept = probs >= CONF_THRESHOLD
    idx = target.index[accept]
    df.loc[idx, "sign_imputed"] = preds[accept]
    df.loc[idx, "sign_prob"] = np.round(probs[accept], 3)

    df.loc[df["sign"].notna(), "sign_source"] = "stenographer"
    df.loc[df["sign_imputed"].notna() & df["sign"].isna() & ~role_locked,
           "sign_source"] = "model"

    df = df.drop(columns=["comment_txt"])
    df.to_csv(OUT / "comments.csv", index=False)

    with open(VAL / "polarity_report.txt", "w") as f:
        f.write("Polarity imputation: TF-IDF (1-2gram) + logistic regression\n")
        f.write(f"training records (signed, text>={MIN_TEXT} chars): {len(train)}\n")
        f.write(f"5-fold CV accuracy: {cv.mean():.3f} (+/- {cv.std():.3f})\n")
        f.write(f"held-out test accuracy: {acc:.3f}\n")
        f.write(f"held-out accuracy at prob>={CONF_THRESHOLD}: {acc_conf:.3f} "
                f"(covers {conf_mask.mean():.1%} of test)\n\n")
        f.write("held-out classification report:\n" + report + "\n")
        f.write("confusion matrix (rows=true +,-,=):\n" + str(cm) + "\n\n")
        f.write(f"unsigned comments with text: {len(target)}\n")
        f.write(f"imputed at prob>={CONF_THRESHOLD}: {int(accept.sum())} "
                f"({accept.mean():.1%})\n")
        f.write(f"unsigned without text (not imputable): "
                f"{int((df['sign'].isna() & ~has_text).sum())}\n")
    print(open(VAL / "polarity_report.txt").read())


if __name__ == "__main__":
    main()
