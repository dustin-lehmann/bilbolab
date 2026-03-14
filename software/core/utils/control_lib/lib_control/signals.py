import numpy as np

def gen_step(duration,dt,start,stop, amplitude):
    t = np.arange(start=0, stop=duration, step=dt)
    N = int(duration * 1/dt)
    y = np.zeros((N,1))
    y[int(start*1/dt):int(stop*1/dt)] = amplitude
    return y,t
