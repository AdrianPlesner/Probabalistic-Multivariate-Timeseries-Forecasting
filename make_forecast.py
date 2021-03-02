from gluonts.model.gp_forecaster import GaussianProcessEstimator
from gluonts.mx.trainer import Trainer
from gluonts.evaluation.backtest import make_evaluation_predictions
import matplotlib.pyplot as plt
from pathlib import Path
from gluonts.model.predictor import Predictor


def train_predictor(data=None, prediction_length=0, freq="1H", train_length=0, metadata=None, estimator=None):
    if metadata is None:
        metadata = {}
    if data is None:
        data = [{}]
    if estimator is None:
        estimator = GaussianProcessEstimator(
            metadata['freq'],
            metadata['prediction_length'],
            1,
            Trainer(ctx="cpu",
                    epochs=10,
                    learning_rate=1e-3,
                    hybridize=False,
                    num_batches_per_epoch=50),
            metadata['train_length']
        )

    assert (len(data) > 0)

    if "prediction_length" not in metadata.keys():
        metadata['prediction_length'] = prediction_length
    assert(metadata['prediction_length'] > 0)

    if "train_length" not in metadata.keys():
        metadata['train_length'] = train_length
    assert(metadata['train_length'] > 0)
    if "freq" not in metadata.keys():
        metadata['freq'] = freq
    metadata['data_sets'] = len(data)
    e = []
    predictor = []

    for n in range(metadata['data_sets']):
        e.append(estimator)
        p = e[n].train(data[n]['train'])
        predictor.append(p)

    return predictor


def make_forecast(predictor, data, metadata):
    metadata['data_sets'] = len(data)
    f = []
    t = []
    f_e = []
    t_e = []
    for n in range(metadata['data_sets']):
        forecast_it, ts_it = make_evaluation_predictions(
            dataset=data[n],  # test dataset
            predictor=predictor[n],  # predictor
            num_samples=100,  # number of sample paths we want for evaluation
        )
        f.append(list(forecast_it))
        t.append(list(ts_it))
        t_e.append(t[n][0])
        f_e.append(f[n][0])
    return t_e, f_e


def plot_prob_forecasts(ts_entry, forecast_entry, num, metadata):
    plot_length = metadata['test_length'] + metadata['train_length']
    prediction_intervals = (50.0, 90.0)
    legend = ["observations", "median prediction"] + [f"{k}% prediction interval" for k in prediction_intervals][::-1]

    fig, ax = plt.subplots(1, 1, figsize=(20, 10))
    ts_entry[-plot_length:].plot(ax=ax)  # plot the time series
    forecast_entry.plot(prediction_intervals=prediction_intervals, color='g')
    plt.grid(which="both")
    plt.legend(legend, loc="upper left")
    plt.title("dataset " + str(num))
    plt.show()


def load_predictors(path, num, sub_paths=None):
    if sub_paths is None:
        sub_paths = []
        for n in range(num):
            sub_paths.append("p" + str(n))

    predictor = []
    for n in range(num):
        predictor.append(Predictor.deserialize(Path(path + sub_paths[n])))

    return predictor
