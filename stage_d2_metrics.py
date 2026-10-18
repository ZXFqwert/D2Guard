"""Frozen three-class metrics. No test-dependent threshold selection."""
import numpy as np

LABELS = ('request', 'quoted', 'none')
OLD_MAP = {'to_agent': 'request', 'for_reader': 'request', 'quoted': 'quoted', 'data': 'none'}


def mapped(rows):
    return [{**r, 'label': OLD_MAP.get(r['label'], r['label'])} for r in rows]


def merge_old(ps):
    ps = np.asarray(ps)
    return np.column_stack([ps[:, 0] + ps[:, 1], ps[:, 2], ps[:, 3]])


def metrics(rows, probabilities, threshold=.5):
    ps = np.asarray(probabilities, dtype=float)
    if ps.shape != (len(rows), 3) or not np.isfinite(ps).all() or (ps < 0).any() or not np.allclose(ps.sum(1), 1, atol=.015):
        raise ValueError('Invalid probability matrix')
    ps = ps / ps.sum(1, keepdims=True)
    y = np.array([LABELS.index(r['label']) for r in rows])
    pred = ps.argmax(1)
    positive = ps[:, 0] >= threshold
    truth, negative = y == 0, y == 2
    tp = int((positive & truth).sum()); fp = int((positive & ~truth).sum()); fn = int((~positive & truth).sum())
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.
    ece = 0.; multiclass_ece = 0.
    for bin_index in range(10):
        for mode in ('binary', 'multiclass'):
            confidence = ps[:, 0] if mode == 'binary' else ps.max(1)
            correct = truth if mode == 'binary' else pred == y
            idx = np.minimum((confidence * 10).astype(int), 9) == bin_index
            if idx.any():
                error = float(idx.mean() * abs(confidence[idx].mean() - correct[idx].mean()))
                if mode == 'binary': ece += error
                else: multiclass_ece += error
    classes = {}
    for i, label in enumerate(LABELS):
        support = int((y == i).sum()); pp = int((pred == i).sum()); correct = int(((y == i) & (pred == i)).sum())
        classes[label] = {'support': support, 'f1': 2 * correct / (support + pp) if support + pp else None}
    return {'n': len(rows), 'request': {'tp': tp, 'fp': fp, 'fn': fn, 'support': int(truth.sum()),
            'precision': precision, 'recall': recall, 'f1': f1, 'threshold': threshold},
            'none_false_positive': int((negative & positive).sum()), 'none_support': int(negative.sum()),
            'none_fpr': float((negative & positive).sum() / negative.sum()) if negative.any() else None,
            'ece_request_10_bins': ece, 'ece_multiclass_10_bins': multiclass_ece,
            'accuracy': float((pred == y).mean()), 'macro_f1_present_classes': float(np.mean([v['f1'] for v in classes.values() if v['support']])), 'classes': classes}


def groups(rows, probabilities, threshold=.5):
    ps = np.asarray(probabilities)
    result = {'all': metrics(rows, ps, threshold)}
    for field in ('evaluation_set', 'language'):
        result[field] = {}
        for value in sorted({r.get(field, 'unspecified') for r in rows}):
            idx = [i for i, r in enumerate(rows) if r.get(field, 'unspecified') == value]
            result[field][value] = metrics([rows[i] for i in idx], ps[idx], threshold)
    return result
