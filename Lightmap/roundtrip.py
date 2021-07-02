import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import histlite as hl
import pandas as pd
import LightMap
import sys
import os
import pickle
import argparse
import time
import gzip
from plot_data import plot_lm_rz,proj2d,make_figs,plot_results

# ***********************************************************************************************************
# SET BASIC RUN OPTIONS HERE
# ***********************************************************************************************************

# save figures here
sim_dir = os.getenv('SIM_DIR')
path = '{}/outputs/'.format(sim_dir)

'''
Arguments:
description    :    The description that will be appended to file names to identify this run
standoff       :    The fiducial cut as a distance from the nearest wall, in mm
events         :    The number of events to be used to reconstruct the lightmap
fit_type       :    The type of fit to apply to the data. Currently 'NN' or 'KS'
-train         :    Run the full NN training. Default is False
-make_plots    :    Show the plots produced rather than just saving them
-both_peaks    :    Train on both Xe-127 peaks. Default is just high energy peak
-learning_rate :    Learning rate input for NN
-layers        :    List of number of nodes per layer. One input for each layer
-batch_size    :    Batch size used in NN training
-ensemble_size :    Number of NNs in the ensemble
-sigma         :    Smoothing length scale for kernel smoother
-seed          :    Random state used to get subset of events from input files
-input_files   :    List of processed simulation files
'''
parser = argparse.ArgumentParser()
parser.add_argument('-input_files',type=str,nargs='+')
parser.add_argument('-train',action='store_true',default=False)
parser.add_argument('-make_plots',action='store_true',default=False)
parser.add_argument('-both_peaks',action='store_true',default=False)
parser.add_argument('-learning_rate',type=float)
parser.add_argument('-layers',type=int,nargs='+')
parser.add_argument('-batch_size',type=int)
parser.add_argument('-ensemble_size',type=int)
parser.add_argument('-sigma',type=float)
parser.add_argument('-seed',type=int,default=1)
parser.add_argument('description',type=str)
parser.add_argument('standoff',type=float)
parser.add_argument('events',type=int)
parser.add_argument('fit_type',type=str)

args = parser.parse_args()
input_files = args.input_files
rt_on = args.train
make_plots = args.make_plots
both_peaks = args.both_peaks
standoff = args.standoff
name = args.description
events = args.events
fit_type = args.fit_type
learning_rate = args.learning_rate
layers = args.layers
batch_size = args.batch_size
ensemble_size = args.ensemble_size
sigma = args.sigma
seed = args.seed

if fit_type!='NN' and fit_type!='KS':
    print('\nFit type not recognized. Exiting.\n')
    sys.exit()

if not make_plots:
    mpl.use('pdf')
    
# **********************************************************************************************************
# DEFINE ANY FUNCTIONS AND SET PLOTTING OPTIONS
# **********************************************************************************************************

# cut to select high energy peak
cl_slope = -0.068
def peak_sep(x):
    return cl_slope*x+1600

# cut out any other peaks
def cl_cut(x,y):
    #       bottom limit         right limit       left limit
    #return (y>cl_slope*x+580) & (y<-x*cl_slope) & (y>-x*cl_slope-790)
    return y>100

# set plotting style
plt.rc('figure', dpi=200, figsize=(4,3), facecolor='w')
plt.rc('savefig', dpi=200, facecolor='w')
plt.rc('lines', linewidth=1.5)
pkw = dict(cmap='viridis',vmin=0., vmax=.5)

# *********************************************************************************************************
# LOAD TPC AND TRUE LIGHTMAP MODEL
# *********************************************************************************************************

# load TPC used for training
print('\nLoading TPC geometry used for lightmap training...\n')
with open(sim_dir+'tpc.pkl', 'rb') as handle:
    tpc = pickle.load(handle)
print(tpc)

# redefine TPC as reduced volume within field rings and between cathode and anode
tpc.r = 566.65
tpc.zmax = -402.97 #tpc.zmax-19.#1199#17#19.
tpc.zmin = -1585.97#tpc.zmax-1183.#3#21#1183.

# load model
print('\nLoading true lightmap model...\n')
lm_true = LightMap.load_model(sim_dir+'true-lm', 'LightMapHistRZ')
print(lm_true, '\n')

# plot the original lightmap
fig,ax = plt.subplots(figsize=(3.5,5))
d = plot_lm_rz(ax,lm_true,tpc)
ax.set_title('True Lightmap')
plt.savefig(path+'original.png',bbox_inches='tight')

# *********************************************************************************************************
# LOOP THROUGH ALL DATASETS
# *********************************************************************************************************

# loop through and collect the specified number of events
data = []
print('Collecting events from {:d} processed simulation files...\n'.format(len(input_files)))
for data_file in input_files:
    input_file = gzip.open(data_file,'rb')
    this_df = pickle.load(input_file)
    data.append(this_df)
    input_file.close()

# add to pandas dataframe
data = pd.concat(data,ignore_index=True)

# get a sample of events from the full set
print('Sampling {:d} events randomly using seed {:d}...\n'.format(events,seed))
data = data.sample(events, random_state=seed)

# compute z from the drift time and TPC dimensions
# drift velocity from 2021 sensitivity paper
# TPC center + (TPC length)/2 - TPC top to anode
# 1022.6 + 1277/2 - 18.87
data['z'] = -402.97 - data.weighted_drift.values*1.709

# *****************************************************************************************************
# APPLY CUTS AND DETERMINE QUANTITIES FOR NN TRAINING
# *****************************************************************************************************

print('Applying quality cuts to the data...\n')

# cut events with no charge signal
data_size = len(data.index)
cuts = ~(data['evt_charge_including_noise']==0)
after_elec = len(data[cuts].index)

# cut events with NaN z values
cuts = cuts & ~(np.isnan(data['z']))
after_drift = len(data[cuts].index)

# cut events with no photons produced
cuts = cuts & ~(data['Observed Light']==0)
after_photon = len(data[cuts].index)

# apply fiducial cut
zlim = [tpc.zmin+standoff,tpc.zmax-standoff]
rlim = [0,tpc.r-standoff]
inside_z = abs(data.z.values-(zlim[1]-zlim[0])/2.-zlim[0])>(zlim[1]-zlim[0])/2.
inside_r = abs(data.weighted_radius.values-(rlim[1]-rlim[0])/2.-rlim[0])>(rlim[1]-rlim[0])/2.
cuts = cuts & (~inside_z & ~inside_r)
after_fiducial = len(data[cuts].index)

# sample based on number of photons generated
qe = 0.1

# separate low and high energy peaks
data['peak'] = np.ones(len(data['Observed Light']))
peak_cond = peak_sep(data.evt_charge_including_noise.values) < data['Observed Light']
data.loc[peak_cond,'peak'] = 2

# cut out data that is not in one of the peaks
cut_cond = cl_cut(data.evt_charge_including_noise.values,data['Observed Light'])
cuts = cuts & cut_cond
after_chargelight = len(data[cuts].index)

# print results of cuts with efficiency
print('Events before thermal electron cut: '+str(data_size))
print('Events after thermal electron cut: '+str(after_elec))
print('Thermal electron cut efficiency: {:.1f} %'.format(after_elec*100./data_size))
print('Events after z quality cut: '+str(after_drift))
print('z quality cut efficiency: {:.1f} %'.format(after_drift*100./after_elec))
print('Events after photon cut: '+str(after_photon))
print('Photon cut efficiency: {:.1f} %'.format(after_photon*100./after_drift))
print('Events after fiducial cut: '+str(after_fiducial))
print('Fiducial cut efficiency: {:.1f} %'.format(after_fiducial*100./after_photon))
print('Events after charge/light cut: '+str(after_chargelight))
print('Charge/light cut efficiency: {:.1f} %\n'.format(after_chargelight*100./after_fiducial))

# compute mean number of photons for each peak
peaks = np.array((0,0))
for j in range(2):
    peaks[j] = np.mean(data['fInitNOP'][(data['peak']==j+1) & cuts])

# compute the efficiency using the predicted mean of each peak
print('Computing the efficiency from the data selected...\n')
data['eff'] = data['Observed Light']/(qe*peaks[np.array(data.peak.values-1,dtype=int)])

np.savetxt(path+'effic_'+name+'.txt',np.array(data.eff.values))

# *****************************************************************************************************
# PLOT ALL DATA BEFORE TRAINING
# *****************************************************************************************************

if make_plots:
    print('Saving some relevant plots in {:s}\n'.format(path))
    make_figs(tpc,lm_true,data,cuts,path,name,rlim,zlim,peak_sep)
    plt.show()

if not rt_on:
    sys.exit()

# *****************************************************************************************************
# FIT A LIGHTMAP MODEL TO THE DATA
# *****************************************************************************************************

# define new training set
if both_peaks == True:
    train_again = data.weighted_x.values[cuts], data.weighted_y.values[cuts], data.z.values[cuts], data.eff.values[cuts]
    print('Training on both peaks with {:d} events total.\n'.format(len(train_again[0])))
else:
    train_again = data.weighted_x.values[(data['peak']==2) & cuts],data.weighted_y.values[(data['peak']==2) & cuts],\
                  data.z.values[(data['peak']==2) & cuts],data.eff.values[(data['peak']==2) & cuts]
    print('Training on one peak with {:d} events total.\n'.format(len(train_again[0])))

# define neural net lightmap
if fit_type=='NN':
    if layers==None:
        layers = [512, 256, 128, 64, 32]
    if learning_rate==None:
        learning_rate = 0.001
    if ensemble_size==None:
        ensemble_size = 3
    if batch_size==None:
        batch_size = 64
    lm_again = LightMap.total.LightMapNN(tpc, epochs=10, batch_size=batch_size,
                                         hidden_layers=layers, lr=learning_rate)

# define Gaussian kernel smoothing lightmap
if fit_type=='KS':
    ensemble_size = 1
    if sigma==None:
        sigma = 50
    lm_again = LightMap.total.LightMapKS(tpc, sigma, points=50, batch_size=1000)

# fit the lightmap
print('Fitting a lightmap to the data...\n')
times = []
for i in range(ensemble_size):
    starttime = time.time()
    lm_again.fit(*train_again)
    endtime = time.time()
    times.append(endtime-starttime)

# save losses for NN model
if fit_type=='NN':
    losses = []
    for i in range(ensemble_size):
        losses.append(np.array(lm_again.histories[i].history['loss']))
else:
    losses = None

# save fitted lightmap
LightMap.save_model(path+'LightMap_'+name,lm_again.kind,lm_again)

# *****************************************************************************************************
# PLOT FINAL LIGHTMAP FOR SIMULATED DATA AND SAVE RESULTS
# *****************************************************************************************************

# make results plots and compute fitting metrics
print('\nPlotting and saving the results...\n')
mean,var = plot_results(tpc,lm_true,lm_again,rlim,zlim,path,name)

# print fitting results
print('Fitting results')
print('-----------------------------')
print('Mean: {:.6f}'.format(mean))
print('Standard deviation: {:.6f}'.format(np.sqrt(var)))
print('-----------------------------\n')

# pickle parameters
params_list = [[name,
                fit_type,
                events,
                standoff,
                int(both_peaks)+1,
                np.array(layers),
                learning_rate,
                ensemble_size,
                batch_size,
                sigma,
                len(train_again[0]),
                np.array(times),
                np.array(losses),
                np.sqrt(var),
                mean
                ]]

columns = ['name',
           'fit_type',
           'nominal_events',
           'fid_cut',
           'num_peaks',
           'layers',
           'learning_rate',
           'ensemble_size',
           'batch_size',
           'sigma',
           'num_events',
           'times',
           'losses',
           'accuracy_std_dev',
           'accuracy_mean'
           ]

params = pd.DataFrame(params_list,columns=columns)
params.to_pickle(path + name + '_results.pkl',compression='gzip')
print('Results saved to {:s}'.format(path+name+'_results.pkl'))

if make_plots:
    plt.show()
