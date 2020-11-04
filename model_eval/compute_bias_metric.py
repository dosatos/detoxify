import pandas as pd
import json 
from tqdm import tqdm
import numpy as np
from sklearn.metrics import roc_auc_score
import json
import argparse

def compute_auc(y_true, y_pred):
    try:
        return roc_auc_score(y_true, y_pred)
    except ValueError:
        return np.nan

def compute_subgroup_auc(df, subgroup, label, model_name):
    subgroup_examples = df[df[subgroup]]
    return compute_auc(subgroup_examples[label], subgroup_examples[model_name])

def compute_bpsn_auc(df, subgroup, label, model_name):
    """Computes the AUC of the within-subgroup negative examples and the background positive examples."""
    subgroup_negative_examples = df[df[subgroup] & ~df[label]]
    non_subgroup_positive_examples = df[~df[subgroup] & df[label]]
    examples = subgroup_negative_examples.append(non_subgroup_positive_examples)
    return compute_auc(examples[label], examples[model_name])

def compute_bnsp_auc(df, subgroup, label, model_name):
    """Computes the AUC of the within-subgroup positive examples and the background negative examples."""
    subgroup_positive_examples = df[df[subgroup] & df[label]]
    non_subgroup_negative_examples = df[~df[subgroup]& ~df[label]]
    examples = subgroup_positive_examples.append(non_subgroup_negative_examples)
    return compute_auc(examples[label], examples[model_name])

def compute_bias_metrics_for_model(dataset,
                                   subgroups,
                                   model,
                                   label_col,
                                   include_asegs=False):
    """Computes per-subgroup metrics for all subgroups and one model."""
    records = []
    for subgroup in subgroups:
        record = {
            'subgroup': subgroup,
            'subgroup_size': len(dataset[dataset[subgroup]])
        }
        record[SUBGROUP_AUC] = compute_subgroup_auc(dataset, subgroup, label_col, model)
        record[BPSN_AUC] = compute_bpsn_auc(dataset, subgroup, label_col, model)
        record[BNSP_AUC] = compute_bnsp_auc(dataset, subgroup, label_col, model)
        records.append(record)
    return pd.DataFrame(records).sort_values('subgroup_auc', ascending=True)

def convert_to_bool(df, col_name):
    df[col_name] = np.where(df[col_name] >= 0.5, True, False)
    
def convert_dataframe_to_bool(df):
    bool_df = df.copy()
    for col in ['toxicity'] + identity_columns:
        convert_to_bool(bool_df, col)
    return bool_df

def calculate_overall_auc(df, model_name):
    true_labels = df[TOXICITY_COLUMN]
    predicted_labels = df[model_name]
    return roc_auc_score(true_labels, predicted_labels)

def power_mean(series, p):
    total = sum(np.power(series, p))
    return np.power(total / len(series), 1 / p)

def get_final_metric(bias_df, overall_auc, POWER=-5, OVERALL_MODEL_WEIGHT=0.25):
    bias_score = np.average([
        power_mean(bias_df[SUBGROUP_AUC], POWER),
        power_mean(bias_df[BPSN_AUC], POWER),
        power_mean(bias_df[BNSP_AUC], POWER)
    ])
    return (OVERALL_MODEL_WEIGHT * overall_auc) + ((1 - OVERALL_MODEL_WEIGHT) * bias_score)

def main():
    with open(TEST, 'r') as f:
        results = json.load(f)
        
    test_private_path = '../jigsaw_data/jigsaw-unintended-bias-in-toxicity-classification/test_private_expanded.csv'
    test_private = pd.read_csv(test_private_path)
    test_private = convert_dataframe_to_bool(test_private)

    test_private[MODEL_NAME] = [s[0] for s in results['scores']]

    bias_metrics_df = compute_bias_metrics_for_model(test_private, identity_columns, MODEL_NAME, TOXICITY_COLUMN)
    print(bias_metrics_df)

    final_metric = get_final_metric(bias_metrics_df, calculate_overall_auc(test_private, MODEL_NAME))
    print(final_metric)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "res_path",
        type=str,
        help="path to the saved results file",
    )
    args = parser.parse_args()

    TEST = '../Jigsaw_ROBERTA_bias/lightning_logs/version_3/checkpoints/epoch=3.results.json'
    # TEST = args.res_path

    identity_columns = [
        'male', 'female', 'homosexual_gay_or_lesbian', 'christian', 'jewish',
        'muslim', 'black', 'white', 'psychiatric_or_mental_illness']

    TOXICITY_COLUMN = 'toxicity'
    MODEL_NAME = 'Roberta'
    SUBGROUP_AUC = 'subgroup_auc'
    
    # stands for background positive, subgroup negative
    BPSN_AUC = 'bpsn_auc'
    
    # stands for background negative, subgroup positive
    BNSP_AUC = 'bnsp_auc'
