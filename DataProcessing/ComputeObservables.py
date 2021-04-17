import numpy as np
import pandas as pd

#####################################################################################
# COMPUTE OBSERVED LIGHT
#####################################################################################
def ComputeObservedLight( dfsim ):
    detected_photons = np.random.binomial(dfsim['fInitNOP'],0.03)
    detected_photoelectrons = detected_photons + \
                                np.random.poisson(detected_photons*0.2)
    return detected_photoelectrons


#####################################################################################
# COMPUTE OBSERVED CHARGE
#####################################################################################
def ComputeObservedCharge( dfelec, channel_threshold=-100000 ):
    
    output_dict = dict()
    
    num_channels_nonzero_charge_with_noise = []
    num_channels_nonzero_charge_excluding_noise = []
    num_channels_in_evt = []
    num_channels_excluding_noise = []
    num_channels_collection = []
    num_collection_below_threshold = []
    num_channels_induction = []
    evt_charge_excluding_noise = []
    evt_charge_including_noise = []
    evt_charge_above_threshold = []
    num_channels_above_threshold = []
    
    weighted_radius = []
    weighted_drift = []
    
    
    counter = 0

    for index,row in dfelec.iterrows():
        
        counter += 1
        if counter % 100000 == 0: print('Event {} at {:4.4}s...'.format(counter,time.time()-start_time))
        
        
        is_noise_channel = []
        drift_times = []
        x_positions = []
        y_positions = []
        x_weights = []
        y_weights = []
        charge_weights = []
        is_x_channel = []
        
        nch = len(row['fElecChannels.fChannelCharge'])
        num_channels_in_evt.append( nch )
        
        

        for i in range(nch):
            
            # Local ID's greater than 15 correspond to Y-channels,
            # otherwise they're x-channels
            if row['fElecChannels.fChannelLocalId'][i] > 15:
                strip_width = 96.
                strip_height = 6.
                xoffset = -96./2.
                yoffset = 0.
            else:
                strip_width = 6.
                strip_height = 96.
                xoffset = 0.
                yoffset = -96./2.
            
            if np.array(row['fElecChannels.fChannelNoiseTag'][i]):
                is_noise_channel.append(True)
            else:
                is_noise_channel.append(False)
                drift_times.append( row['fElecChannels.fChannelTime'][i] \
                                    + np.random.normal(0.,2.) )
                x_positions.append( row['fElecChannels.fXPosition'][i] + xoffset )
                y_positions.append( row['fElecChannels.fYPosition'][i] + yoffset )
                x_weights.append(1./strip_width)
                y_weights.append(1./strip_height)
                charge_weights.append( row['fElecChannels.fChannelCharge'][i] )
                if row['fElecChannels.fChannelLocalId'][i] > 15:
                    is_x_channel.append(True)
                else: 
                    is_x_channel.append(False)

        is_noise_channel = np.array(is_noise_channel) 
        drift_times = np.array(drift_times)
        x_positions = np.array(x_positions)
        y_positions = np.array(y_positions)
        charge_weights = np.array(charge_weights)
        x_weights = np.array(x_weights)
        y_weights = np.array(y_weights)
        
        weighted_x = np.sum(x_positions*(charge_weights*x_weights))/np.sum(charge_weights*x_weights)
        weighted_y = np.sum(y_positions*(charge_weights*y_weights))/np.sum(charge_weights*y_weights)
        
        weighted_radius.append( np.sqrt(weighted_x**2 + weighted_y**2) )
        weighted_drift.append(\
                             np.sum(drift_times*charge_weights)/np.sum(charge_weights)
                             )
        
        
        nonzero_mask = np.invert(row['fElecChannels.fChannelCharge']==0) # true if collection


        fluctuated_charge = np.random.normal(0.,600.,size=nch)\
                            + row['fElecChannels.fChannelCharge']
        threshold_mask = fluctuated_charge>channel_threshold

        num_channels_nonzero_charge_with_noise.append( np.sum(nonzero_mask) )
        num_channels_nonzero_charge_excluding_noise.append( \
                                                np.sum( nonzero_mask & np.invert(is_noise_channel) )\
                                                          )
        evt_charge_including_noise.append(   np.sum(row['fElecChannels.fChannelCharge'][nonzero_mask]) )
        evt_charge_excluding_noise.append(   np.sum(row['fElecChannels.fChannelCharge'][nonzero_mask & np.invert(is_noise_channel)]) )
        evt_charge_above_threshold.append(   np.sum( fluctuated_charge[ threshold_mask & np.invert(is_noise_channel) ] ) )
        num_channels_above_threshold.append( np.sum( threshold_mask & np.invert(is_noise_channel) ))
        num_channels_excluding_noise.append( np.sum( np.invert(is_noise_channel) ) )
        num_channels_collection.append(      np.sum( np.invert(is_noise_channel) & nonzero_mask ) )
        num_collection_below_threshold.append( np.sum( np.invert(is_noise_channel) & nonzero_mask & np.invert(threshold_mask) ) )
        num_channels_induction.append(       np.sum( np.invert(is_noise_channel) & np.invert(nonzero_mask) ) )                          

    output_dict['num_channels_in_evt'] = np.array(num_channels_in_evt)
    output_dict['evt_charge_including_noise'] = np.array(evt_charge_including_noise)
    output_dict['evt_charge_excluding_noise'] = np.array(evt_charge_excluding_noise)
    output_dict['evt_charge_above_threshold'] = np.array(evt_charge_above_threshold)
    output_dict['num_channels_above_threshold'] = np.array(num_channels_above_threshold)
    output_dict['num_channels_excluding_noise'] = np.array(num_channels_excluding_noise)
    output_dict['num_channels_collection'] = np.array(num_channels_collection)
    output_dict['num_collection_below_threshold'] = np.array(num_collection_below_threshold)
    output_dict['num_channels_induction'] = np.array(num_channels_induction)
    output_dict['weighted_radius'] = np.array(weighted_radius)
    output_dict['weighted_drift'] = np.array(weighted_drift)
    

    output_dict['num_channels_nonzero_charge_with_noise'] = \
                    np.array(num_channels_nonzero_charge_with_noise)
    output_dict['num_channels_nonzero_charge_excluding_noise'] = \
                    np.array(num_channels_nonzero_charge_excluding_noise)
    
    return output_dict
