import pts
from gluonts.model.gp_forecaster import GaussianProcessEstimator
from gluonts.model.deep_factor import DeepFactorEstimator
from gluonts.model.deepar import DeepAREstimator
from gluonts.mx.distribution import StudentTOutput, MultivariateGaussianOutput, LowrankMultivariateGaussianOutput, \
    GammaOutput, BetaOutput, GenParetoOutput, LaplaceOutput, NegativeBinomialOutput, UniformOutput, BinnedOutput, \
    PoissonOutput, BoxCoxTransformOutput, DirichletMultinomialOutput, LogitNormalOutput, \
    DeterministicOutput
from gluonts.mx.kernels import RBFKernelOutput, PeriodicKernelOutput
from gluonts.mx.trainer import Trainer
import matplotlib.pyplot as plt
from pathlib import Path
from gluonts.model.predictor import Predictor
import data_processing as dp
import numpy as np
import pandas as pd
import mxnet as mx
from pts.model.tempflow import TempFlowEstimator
import torch
from gluonts.dataset.multivariate_grouper import MultivariateGrouper
import gluonts.time_feature as time
from matplotlib.dates import HourLocator


def train_predictor(data=None, md=None):
    if md is None:
        exit("Missing metadata for training")
    if data is None:
        exit("Missing data for training")
    trainer = Trainer(ctx=mx.context.gpu(),
                      epochs=50,
                      batch_size=32,
                      learning_rate=1e-3,
                      hybridize=False,
                      num_batches_per_epoch=1143)
    if 'distribution' in md.keys():
        if md['distribution'] == "StudentT":
            distribution = StudentTOutput()
        elif md['distribution'] == "Gaussian":
            distribution = MultivariateGaussianOutput(md['sensors'])
        elif md['distribution'] == "Gamma":
            distribution = GammaOutput()
        elif md['distribution'] == 'Beta':
            distribution = BetaOutput()
        elif md['distribution'] == 'GenPareto':
            distribution = GenParetoOutput()
        elif md['distribution'] == 'Laplace':
            distribution = LaplaceOutput()
        elif md['distribution'] == 'NegativeBinomial':
            distribution = NegativeBinomialOutput()
        elif md['distribution'] == 'Uniform':
            distribution = UniformOutput()
        elif md['distribution'] == 'Poisson':
            distribution = PoissonOutput()
        elif md['distribution'] == 'BoxCox':
            distribution = BoxCoxTransformOutput()
        elif md['distribution'] == 'LogitNormal':
            distribution = LogitNormalOutput()
        else:
            distribution = None
    if md['estimator'] is None or md['estimator'] == "GP":
        if md['kernel'] == "RBF":
            kernel = RBFKernelOutput()
        else:
            kernel = PeriodicKernelOutput()
        estimator = GaussianProcessEstimator(
            freq=md['freq'],
            prediction_length=md['prediction_length'],
            context_length=md['prediction_length'],
            cardinality=md['sensors'],
            trainer=trainer,
            kernel_output=kernel,
            time_features=[time.DayOfWeek(), time.HourOfDay(), time.MinuteOfHour()]

        )
    elif md['estimator'] == "DeepFactor":
        estimator = DeepFactorEstimator(
            freq=md['freq'],
            prediction_length=md['prediction_length'],
            trainer=trainer,
            context_length=md['prediction_length'],
            cardinality=list([md["sensors"]]),
            num_hidden_global=md['global_units'],
            num_layers_global=md['global_layers'],
            num_factors=md['factors'],
            num_hidden_local=md['local_units'],
            num_layers_local=md['local_layers'],
            cell_type=md["cell_type"],
            distr_output=distribution
        )
    elif md['estimator'] == "DeepAR":
        estimator = DeepAREstimator(
            freq=md['freq'],
            prediction_length=md['prediction_length'],
            trainer=trainer,
            context_length=md['prediction_length'],
            num_layers=md['layers'],
            num_cells=md['cells'],
            cell_type=md['cell_type'],
            dropout_rate=md['dropout_rate'],
            use_feat_static_real=False,
            distr_output=distribution,
            time_features=[time.DayOfWeek(), time.HourOfDay(), time.MinuteOfHour()]
        )
    elif md['estimator'] == "TempFlow":
        trainer = pts.Trainer(
            device=torch.device('cuda'),
            epochs=40,
            batch_size=32,
            learning_rate=1e-3,
            num_batches_per_epoch=1143
        )
        estimator = TempFlowEstimator(
            input_size=(2*md['sensors'])+3,
            freq=md['freq'],
            prediction_length=md['prediction_length'],
            target_dim=md['sensors'],
            trainer=trainer,
            context_length=md['prediction_length'],
            num_layers=md['layers'],
            num_cells=md['cells'],
            cell_type=md['cell_type'],
            cardinality=[1],
            flow_type=md['flow'],
            n_blocks=md['blocks'],
            hidden_size=md['hidden_size'],
            n_hidden=md['num_hidden'],
            dropout_rate=md['dropout_rate'],
            conditioning_length=md['conditioning'],
            num_parallel_samples=100,
            time_features=[time.DayOfWeek(), time.HourOfDay(), time.MinuteOfHour()]
        )
        grouper_train = MultivariateGrouper(max_target_dim=md['sensors'])
        data = grouper_train(data)
    else:
        estimator = None
        exit("Invalid estimator")

    assert (len(data) > 0)

    return estimator.train(data)


def make_forecast(predictor, data, md):
    if md['estimator'] == 'TempFlow':
        grouper_train = MultivariateGrouper(max_target_dim=md['sensors'])
        data = grouper_train(data)
    return list(predictor.predict(data, num_samples=250))


make_forecast_vector = np.vectorize(make_forecast, otypes=[list])


def plot_forecast(train, true, forecast_entry, num, md, evalu):
    plot_length = md['prediction_length'] * 12
    prediction_intervals = (90.0, 50.0)
    legend = ["observations", "mean prediction"] + [f"{k}% prediction interval" for k in prediction_intervals][::-1]
    data = [pd.date_range(start=train.list_data[0]['start'], freq=md['freq'], periods=plot_length),
            np.hstack([train.list_data[num]['target'], true.list_data[num]['target']])]
    fig, ax = plt.subplots(1, 1, figsize=(8, 4))
    plt.xlabel('Date [mm-dd hh]')
    plt.ylabel('Speed [mph]')
    plt.plot(data[0], data[1])
    plt.plot(data[0][md['prediction_length']:plot_length], forecast_entry.mean[num], color='#008000')
    y1, y2 = dp.make_prediction_interval(forecast_entry.samples[num], 50)
    plt.fill_between(data[0][md['prediction_length']:plot_length], y1, y2, color='#00800080')
    y1, y2 = dp.make_prediction_interval(forecast_entry.samples[num], 90)
    plt.fill_between(data[0][md['prediction_length']:plot_length], y1, y2, color='#00800060')
    plt.grid(which="both")
    ax.xaxis.set_minor_locator(HourLocator())

    plt.legend(legend, loc="lower left")
    plt.title(f"{md['estimator']}, sensor: {num}, CRPS {evalu}")
    plt.show()
    #    plt.savefig(md['deserialize_path'] + "pictures/" + str(num) + "/" + path)
    plt.close()


def load_predictor(path, md):
    if md['estimator'] == 'TempFlow':
        gpu = torch.cuda.is_available()
        p = Predictor.deserialize(Path(path), device=torch.device('cuda') if gpu else torch.device('cpu'))
    else:
        p = Predictor.deserialize(Path(path))
        p.prediction_net.ctx = p.ctx
    return p
