# -*- coding: utf-8 -*-
"""
Created on Mon Jun 06 12:08:01 2016

@author: Daniel
"""
from numpy import min, max, zeros, reshape, r_
import numpy as np
from scipy.signal import welch
from scipy.ndimage.measurements import label
from skimage.morphology import watershed
from skimage.feature import peak_local_max
from scipy.ndimage.filters import gaussian_filter
from scipy.ndimage.filters import median_filter

def HALS4activity(data, S, activity,NonNegative,lam1_t,lam2_t,iters=1):
    
#        ind=np.squeeze(np.sum(S,0)>0) # find spatial support of components
#        
#        if np.sum(ind)<0.1*np.size(ind):
#            data_comp=np.compress(ind,data,axis=1) # throw away all joint zeros
#            S_comp=np.compress(ind,S,axis=1)
#            
#            A = S_comp.dot(data_comp.T)
#            B = S_comp.dot(S_comp.T)
#        else:
    A = S.dot(data.T)
    B = S.dot(S.T)

    for _ in range(iters):
        for ll in range(len(S)):
            activity[ll] += np.nan_to_num((A[ll] - np.dot(B[ll].T, activity)-lam1_t-lam2_t*activity[ll]  ) / B[ll, ll]) #maybe multiply lam1_t by np.sign[activity[ll]?
            if NonNegative:
                activity[ll][activity[ll] < 0] = 0
    return activity
    
#    @profile
def HALS4shape(data, S, activity,mask,lam1_s,lam2_s,adaptBias,iters=1):    
#        ind=np.squeeze(np.sum(activity,0)>0) # find spatial support of components
#        
#        if np.sum(ind)<0.1*np.size(ind):
#            data_comp=np.compress(ind,data,axis=0) # throw away all joint zeros
#            activity_comp=np.compress(ind,S,axis=1)
#            
#            C = activity_comp.dot(data_comp)
#            D = activity_comp.dot(activity_comp.T)
#        else:
    C = activity.dot(data)
    D = activity.dot(activity.T)
    L=len(activity)
    for _ in range(iters):
        for ll in range(L-adaptBias):
            if ll == L:
                S[ll] += np.nan_to_num((C[ll] - np.dot(D[ll], S)-lam1_s[ll]-lam2_s*S[ll]) / D[ll, ll])
            else:
                S[ll, mask[ll]] += np.nan_to_num((C[ll, mask[ll]]
                                               - np.dot(D[ll], S[:, mask[ll]])-lam1_s[ll,mask[ll]]-lam2_s*S[ll,mask[ll]])/ D[ll, ll])
#                if NonNegative:
            S[ll][S[ll] < 0] = 0
    # normalize/delete components

    return S 
    
def RenormalizeDeleteSort( S, activity, mask,centers,boxes,ES,adaptBias,MedianFilt):
    L=len(S)-adaptBias
    deleted_indices=[]
    
    ## Go over shapes
    for ll in range(L + adaptBias):
        if MedianFilt==True:
            S[ll]=median_filter(S[ll],3)
        if ll<L:
            S_normalization=np.sum(S[ll,mask[ll]])
        else:
            S_normalization=np.sum(S[ll])
        A_normalization=np.sum(activity[ll])
        if A_normalization>0:
            activity[ll]=activity[ll]/A_normalization 
            S[ll]=S[ll]*A_normalization 
        if ll<L: # don't delete background component
            if ((A_normalization<=0) and (S_normalization<=0)):
                deleted_indices.append(ll)      
    
    #delete components with zero activity AND zero shape (these will never become non-zero again)
    for ll in deleted_indices[::-1]:     
        S=np.delete(S,(ll),axis=0)
        activity=np.delete(activity,(ll),axis=0)
        del mask[ll]
        centers=np.delete(centers,(ll),axis=0)
        boxes=np.delete(boxes,(ll),axis=0)
        ES.delete(ll)
    L=len(S)-adaptBias
    
    #sort components according to magnitude
    magnitude=np.sum(S[:L],axis=1)*np.max(activity[:L],axis=1)
    sort_indices = np.argsort(magnitude)[::-1]
    centers=centers[sort_indices]
    boxes=boxes[sort_indices]
    mask=[mask[ii] for ii in sort_indices]      
    
    if adaptBias:
        sort_indices=np.append(sort_indices,L)
    activity=activity[sort_indices]
    S=S[sort_indices]
    ES.reorder(sort_indices)
            
    return  S, activity, mask,centers,boxes,ES,L

def addComponent(new_cent,current_data,data_dim,box_size,S, activity, mask,centers,boxes,adaptBias):
    new_activity=current_data[:,new_cent]-np.dot(activity.T,S[:,new_cent])
    #       new_activity=np.random.randn(data_dim[0]) # for testing purposes only
    activity=np.insert(activity,0,new_activity,axis=0)
    S=np.insert(S,0,0*current_data[0,:].reshape(1,-1),axis=0) 
    centers=np.insert(centers,0,np.unravel_index(new_cent,data_dim[1:]),axis=0)
    boxes=np.insert(boxes,0,GetBox(centers[0], box_size, data_dim[1:]),axis=0)
            
    temp = zeros(data_dim[1:])
    temp[map(lambda a: slice(*a), boxes[0])]=1
    temp2=np.where(temp.ravel())[0]
    mask.insert(0,temp2)
    
    L=len(S)-adaptBias
    
    return  S, activity, mask,centers,boxes,L

def GetBox(centers, R, dims):
    D = len(R)
    box = zeros((D, 2), dtype=int)
    for dd in range(D):
        box[dd, 0] = max((centers[dd] - R[dd], 0))
        box[dd, 1] = min((centers[dd] + R[dd] + 1, dims[dd]))
    return box

def RegionAdd(Z, X, box):
    # Parameters
    #  Z : array, shape (T, X, Y[, Z]), dataset
    #  box : array, shape (D, 2), array defining spatial box to put X in
    #  X : array, shape (T, prod(diff(box,1))), Input
    # Returns
    #  Z : array, shape (T, X, Y[, Z]), Z+X on box region
    Z[[slice(len(Z))] + list(map(lambda a: slice(*a), box))
      ] += reshape(X, (r_[-1, box[:, 1] - box[:, 0]]))
    return Z


def RegionCut(X, box):
    # Parameters
    #  X : array, shape (T, X, Y[, Z])
    #  box : array, shape (D, 2), region to cut
    # Returns
    #  res : array, shape (T, prod(diff(box,1))),
    dims = X.shape
    return X[[slice(dims[0])] + list(map(lambda a: slice(*a), box))].reshape((dims[0], -1))
    
def DownScale(data,mb,ds):
    """
        Parameters
        ----------
        data : array, shape (T, X, Y[, Z])
            block of the data
        mbs : int
            minibatchsizes for temporal downsampling 
        ds : list/vector or int
            factor for spatial downsampling - must divide X,Y and Z! 
            if list/vector, length equal the number spatial dimensions in data
    
        Returns
        -------
        data0 : array, shape (T/mb, (X/ds[0])*(Y/ds[1])[*(Z/ds[2])])
            downscaled block of the data
        dims0 : array, vector
            original dimensions of the data0

        """
    if ds==1 and mb==1:
        data0=data
    else:
        dims = data.shape
        D = len(dims)
        if type(ds)==int:
            ds=ds*np.ones(D-1)
        elif (len(ds)!=D-1):
            print "either type(ds)==int, or len(ds)== the number of spatial dimensions in data"
            return
        data0 = data[:int(len(data) / mb) * mb].reshape((-1, mb) + data.shape[1:]).mean(1)
        if D == 4:
            data0 = data0[:,:int(dims[1] /ds[0]) *ds[0],:int(dims[2] /ds[1]) *ds[1],:int(dims[3] /ds[2]) *ds[2]].reshape(
                len(data0), dims[1] / ds[0], ds[0], dims[2] / ds[1], ds[1], dims[3] / ds[2], ds[2])\
                .mean(2).mean(3).mean(4)
        else:
            data0 = data0[:,:int(dims[1] /ds[0]) *ds[0],:int(dims[2] /ds[1]) *ds[1]].reshape(len(data0), dims[1] / ds[0], ds[0], dims[2] / ds[1], ds[1]).mean(2).mean(3)
        # for i,d in enumerate(dims[1:]):
        #     data0 = data0.reshape(data0.shape[:1+i] + (d / ds, ds, -1)).mean(2+i)

                
    dims0 = data0.shape
        
    return data0,dims0
    
def LargestConnectedComponent(shapes,dims,skipBias): 
    L=len(shapes)-skipBias     
    shapes=shapes.reshape((-1,) + dims[1:])    
    structure=np.ones(tuple(3*np.ones((np.ndim(shapes)-1,1))))
    for ll in range(L): 
        temp=np.copy(shapes[ll])
        CC,num_CC=label(temp,structure)
        sz=0
        ind_best=0
        for nn in range(num_CC):
            current_sz=np.count_nonzero(CC[CC==(nn+1)])
            if current_sz>sz:
                ind_best=nn+1
                sz=current_sz
        temp[CC!=ind_best]=0
        shapes[ll]=np.copy(temp)
    shapes=shapes.reshape((len(shapes),-1))
    return shapes
    
#def LargestWatershedRegion(shapes,dims,skipBias):   % Phil's version - good for his C elegance data?
#    L=len(shapes)-skipBias     
#    shapes=shapes.reshape((-1,) + dims[1:]) 
#    D=len(dims)
#    num_peaks=2
##    structure=np.ones(tuple(3*np.ones((np.ndim(shapes)-1,1))))
#    for ll in range(L): 
#        temp=shapes[ll]
#        local_maxi = peak_local_max(gaussian_filter(temp,[1]*(D-1)), exclude_border=False, indices=False, num_peaks=num_peaks)
#        markers,junk = label(local_maxi)
#        nonzero_mask=temp>0
#        if np.sum(nonzero_mask)>(3**3)*num_peaks:
#            labels = watershed(-temp, markers, mask=nonzero_mask)        #watershed regions
#            temp[labels!=1]=0
#            shapes[ll]=temp
#    shapes=shapes.reshape((len(shapes),-1))
#    return shapes
    
def LargestWatershedRegion(shapes,dims,skipBias): 
    L=len(shapes)-skipBias     
    shapes=shapes.reshape((-1,) + dims[1:]) 
    D=len(dims)
    num_peaks=2
#    structure=np.ones(tuple(3*np.ones((np.ndim(shapes)-1,1))))
    for ll in range(L): 
        temp=shapes[ll]
        local_maxi = peak_local_max(gaussian_filter(temp,[1]*(D-1)), exclude_border=False, indices=False, num_peaks=num_peaks)
        markers,junk = label(local_maxi)
        nonzero_mask=temp>0
        if np.sum(nonzero_mask)>(3**3)*num_peaks:
            labels = watershed(-temp, markers, mask=nonzero_mask) #watershed regions
            ind = 1
            temp2 = np.copy(temp)
            temp2[labels!=1]=0
            total_intensity = sum(temp2.reshape(-1,))
            for kk in range(2,labels.max()+1):
                temp2 = np.copy(temp)
                temp2[labels!=kk]=0
                total_intensity2 = sum(temp2.reshape(-1,))
                if total_intensity2>total_intensity:
                    ind = kk
                    total_intensity=total_intensity2
            temp[labels!=ind]=0
            shapes[ll]=temp
    shapes=shapes.reshape((len(shapes),-1))
    return shapes  
    
    
def SmoothBackground(shapes,dims,adaptBias,sig_filt): 
    num_peaks=2
    thresh=0.6
    if adaptBias==True:
        temp=gaussian_filter(shapes[-1].reshape(dims[1:]),sig_filt)
        local_maxi = peak_local_max(temp, exclude_border=False, indices=False, num_peaks=num_peaks)
        markers,num_markers = label(local_maxi)
        if num_markers>1:
            foo=gaussian_filter(1.0*(markers==1),sig_filt)
            nonzero_mask=(foo/np.max(foo))>thresh

            temp2=shapes[-1].reshape(dims[1:])
            temp2[nonzero_mask]=0
#            labels = watershed(-temp, markers, mask=nonzero_mask)        #watershed regions
#            temp2[labels==1]=0
            shapes[-1]=np.ndarray.flatten(temp2)
    return shapes
    
# Estimate noise level for a time series
def GetSnPSD(Y):
    L = len(Y)
    ff, psd_Y = welch(Y, nperseg=round(L / 8))
    sn = np.sqrt(np.mean(psd_Y[ff > .3] / 2))
    return sn

# Estimate noise level for an array of time series
def GetSnPSDArray(Y,f_low=10,f_high=0.6):
    print "Calculating noise level..."
    N = len(Y)
    fmin=np.round(f_high*N/2)
    fmax=np.round(N/2) #maximal frequency is at N/2 - the rest is just symmetric
#        try:
#            psd_Y = (np.abs(np.fft.fft(Y, axis=0))**2)/N
#        except MemoryError:
    psd_Y=np.copy(Y)
    if np.ndim(Y)==2:
        M=Y.shape[1]
        for kk in range(M):
            psd_Y[:,kk] = (np.abs(np.fft.fft(Y[:,kk]))**2)/N
            counter=(kk/float(M))*100
            if (counter%10)==0:
                print counter,'%'
#            else: 
#                raise
    sn=np.sqrt(psd_Y[fmin:fmax].mean(0))+np.sqrt(2*psd_Y[1:f_low].sum(0))/N # white noise + low freq stuff
    sn_std=0.5*sn/np.sqrt(N)
    print "Done"
    return sn,sn_std

class ExponentialSearch:
    def __init__(self,lam,rho=1.5):
        # lam - an array of parameter values
        self.lam=lam
        self.lam_high=-np.ones_like(lam)
        self.lam_low=np.copy(self.lam_high)
        self.rho=rho #exponential search parameters
    
    def update(self,decrease,increase):
        ''' decrease - an array the sFize of lambda
                indicates which lam values should decrease
            increase - an array the size of lambda
                indicates which lam values should increase
        '''
        self.lam_high[decrease]=self.lam[decrease]
        self.lam_low[increase]=self.lam[increase]
        cond1=(self.lam_high==-1)
        cond2=(self.lam_low==-1)
        cond3=np.logical_not(np.logical_or(cond1,cond2))
        self.lam[cond1]=self.lam[cond1]*self.rho
        self.lam[cond2]=self.lam[cond2]/self.rho
        self.lam[cond3]=(self.lam_high[cond3]+self.lam_low[cond3])/2
        
    def delete(self,index):
        ''' delete lam,lam_high,lam_low for given index
        '''
        self.lam_high=np.delete(self.lam_high,(index),axis=0)
        self.lam_low=np.delete(self.lam_low,(index),axis=0)
        self.lam=np.delete(self.lam,(index),axis=0)
    
    def reorder(self,indices):
        ''' reorder lam,lam_high,lam_low accodring to given indices
        '''
        self.lam_high=self.lam_high[indices]
        self.lam_low=self.lam_low[indices]
        self.lam=self.lam[indices]
        
def GrowMasks(shapes,mask,boxes,dims,skipBias,sigma): 
    ''' Grow/shrink masks according to support of non-zero shapes
        Sigma - scalar that determines the size of the boundary around each shape  
    ''' 
    
    L=len(shapes)-skipBias     
    shapes=shapes.reshape((-1,) + dims[1:]) 
    D=len(dims)
    #    structure=np.ones(tuple(3*np.ones((np.ndim(shapes)-1,1))))
    for ll in range(L): 
        temp=0*shapes[ll]
        temp[shapes[ll]>0]=1
        temp2=gaussian_filter(temp,[sigma]*(D-1))
        temp3=temp2>0.5/(np.sqrt(2*np.pi)*sigma)**(D-1)
#        temp3[map(lambda a: slice(*a), boxes[ll])]=1 #make sure mask does not shrink below original support
        mask[ll]=np.where(temp3.ravel())[0]

    shapes=shapes.reshape((len(shapes),-1))
    return mask
#%% Obselete functions
      
#def HALS(data, S, activity, skip=[], check_skip=0, iters=1,NonNegative=True,L,lam1_t,lam2_t):
#    idx = np.asarray(filter(lambda x: x not in skip, range(len(activity))))
#    A = S[idx].dot(data.T)
#    B = S[idx].dot(S.T)
#    noise = zeros(L)
#
#    for ii in range(iters):
#        for k, ll in enumerate(idx):
#            if check_skip and ii == iters - 1:
#                a0 = activity[ll].copy()
#            activity[ll] += nan_to_num((A[k] - np.dot(B[k], activity)-lam1_t-lam2_t*activity[ll]) / B[k, ll])
#            if NonNegative:
#                activity[ll][activity[ll] < 0] = 0
#        # skip neurons whose shapes already converged
#            if check_skip and ll < L and ii == iters - 1:
#                if check_skip == 1:  # compute noise level only once
#                    noise[ll] = GetSnPSD(a0) / a0.mean()
#                if np.allclose(a0, activity[ll] / activity[ll].mean(), 1e-4, noise[ll]):
#                    skip += [ll]
#    C = activity[idx].dot(data)
#    D = activity[idx].dot(activity.T)
#
#    for _ in range(iters):
#        for k, ll in enumerate(idx):
#            if ll == L:
#                S[ll] += nan_to_num((C[k] - np.dot(D[k], S)) / D[k, ll])
#            else:
#                S[ll, mask[ll]] += nan_to_num((C[k, mask[ll]]
#                                               - np.dot(D[k], S[:, mask[ll]])-lam1_s[ll,mask[ll]]-lam2_s*S[ll, mask[ll]]) / D[k, ll])
#            if NonNegative:
#                S[ll][S[ll] < 0] = 0
#
#    return S, activity, skip
#    
#def HALS4lam(data, S, activity,mask):
#    C = activity.dot(data)
#    D = activity.dot(activity.T)
#    temp=np.copy(S[:L])*0
#    for ll in range(L):
#        temp[ll,mask[ll]] = C[ll, mask[ll]]- np.dot(D[ll], S[:, mask[ll]])-lam2_s*S[ll,mask[ll]]
#        temp[temp<0]=0
#    lam=temp.mean(0)+0.001
#
#    return lam