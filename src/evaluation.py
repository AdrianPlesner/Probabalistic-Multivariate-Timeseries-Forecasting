import numpy as np
import properscoring as ps
import pandas as pd
from gluonts.dataset.common import ListDataset
import multiprocessing as mp
import time
import scipy.integrate as integrate


def evaluate_forecast(data, forecast, length):
    observation = data.list_data[0]['target'].reshape(-1, 1)[-length:]
    mean = forecast.mean
    std = np.std(forecast.samples, axis=0)
    e = ps.crps_gaussian(observation, mean, std)
    return np.average(e)


def split_validation(data, md):
    step = md['prediction_length']
    t = pd.date_range(start=data.list_data[0]['start'], freq=md['freq'], periods=len(data.list_data[0]['target']))
    return [ListDataset([{
        'start': t[n],
        'target': d['target'][n:n + step],
        'sensor_id': d['sensor_id'][n:n + step],
        'time_feat': d['time_feat'][::, n:n + step],
        'scaler': d['scaler']
    } for d in data.list_data], freq=md['freq']) for n in range(0, len(t), step)]


def validate(data, forecast):
    print(f'Beginning data with start {data.list_data[0]["start"]}')
    start = time.perf_counter()
    x = [np.sort(n.samples, 0) for n in forecast]
    evaluation = []
    for n in range(len(x)-1):
        ar = x[n].swapaxes(0, 1)
        cdf = [CdfShell(a) for a in ar]
        b = crps_vector(data.list_data[n]['target'], cdf)
        evaluation.append(b)
    end = time.perf_counter() - start
    print(f'Data with start {data.list_data[0]["start"]} done. Time = {end}')
    return np.asarray(evaluation)


validate_vector = np.vectorize(validate, otypes=[list])


def validate_mp(data, forecast):
    assert len(data) == len(forecast)
    n_proc = mp.cpu_count()
    chunk_size = len(data) // n_proc
    rem = len(data) % n_proc
    proc_chunks = []
    # split in chunks for parallelization
    for i_proc in range(n_proc):
        chunkstart = i_proc * chunk_size
        if i_proc < rem:
            chunkstart += i_proc
        else:
            chunkstart += rem
        # make sure to include the division remainder for the last process
        chunkend = (i_proc + 1) * chunk_size
        if i_proc < rem:
            chunkend += i_proc + 1
        else:
            chunkend += rem

        proc_chunks.append((data[chunkstart:chunkend], forecast[chunkstart:chunkend]))

    assert sum([len(x[0]) for x in proc_chunks]) == len(data)

    with mp.Pool(processes=n_proc) as pool:
        # starts the sub-processes without blocking
        # pass the chunk to each worker process
        proc_results = [pool.apply_async(validate_vector, args=(chunk[0], chunk[1],)) for chunk in proc_chunks]

        result_chunks = []
        # blocks until all results are fetched
        for r in proc_results:
            result_chunks.append(r.get())
    result = np.array([])
    for n in result_chunks:
        result = np.append(result, n)
    return result


def _crps(val, a):
    x = a.x
    y = a.y
    split = np.searchsorted(x, val)
    if split < 0:
        split = 0
    if split == len(x):
        split -= 1
    lhs = np.square(y[:split])
    rhs = np.square(1 - y[split:])
    if len(lhs) == 0:
        lc = 0
    else:
        lc = integrate.simpson(lhs, x[:split], even="first")
    if len(rhs) == 0:
        rhs == 0
    else:
        rc = integrate.simpson(rhs, x[split:], even="first")
    return lc + rc


crps_vector = np.vectorize(_crps, otypes=[list])


class CdfShell:
    def __init__(self, a):
        self.x = a
        self.y = np.arange(len(a)) / float(len(a))

    x = []
    y = []

    def cdf(self, a):
        v = np.searchsorted(self.x, a, 'left')
        if v == len(self.y):
            return 1.0
        return self.y[v]
