#!/usr/bin/env python

import sys
import os
from astropy.io import fits
import numpy as np
import time
import scipy.signal
import pyami.simcode.utils as U 


"""
# GLOBALS now contained in utils.py, imported as U.*   anand@stsci.edu Mar 2016
readnoise = cdsreadnoise/np.sqrt(2)      #read noise for one frame
darkcurrent = 0.012                      #0.012 e-/sec 
background = 0.125                       #0.125 e-/sec 
ips_size = 256                           #holdover from before AMISUB became 80x80, maybe fix later
flat_sigma = 0.001                       #flat field error
pixscl = 0.065 #arcsec/pixel - pixel scale used by DL
"""


def adjustsizes(skyov, psfov, ov):
    """
	skyov is 'infinite resolution'.  PSF introduces resolution.
    Enforce divisibility of oversampled arrays by oversample
    Enforce oddness of number of detector pixels in scene
	Make more accomodating later...
    """
    if psfov.shape != skyov.shape:
        print psfov.shape, skyov.shape
        sys.exit("error: oversampled sky and psf must be same-sized arrays")
	
    if skyov.shape[0]%ov != 0:
        sys.exit("error: oversample must exactly divide sky scene array size")

    fovdet = skyov.shape[0] // ov
    print fovdet, "= FOV in detector pixels"

    if fovdet%2 == 1:
        halfdim = (fovdet - 1) // 2
        print halfdim, "= halfdim in detector pixels"
    else:
        sys.exit("error: unable to deal with even dimensional detector array (yet)")

    fovov = skyov.shape[0]
    ipsov = np.ones((U.ips_size*ov, U.ips_size*ov))

    print "psfov.sum(), skyov.sum() are:",
    print "%.2e"%psfov.sum(), " and  %.2e"%skyov.sum() # around 0.15 or less for psf tot.
    # sky tot depends on scene.  Power multiplication theorem applies to
    # the following fftconvolve()
    # Conservation of energy slightly compromised by the "same" mode in the
    # convolution, hopefully only slightly so.
	# This is a caveat on crowded scenes... you can't fill the fov with light
	# and truncate cleanly.  You'll have to simulate a wider FOV than you are
	# interested in if it's important.  Check w/an fft guru if you need.
	#
	# Introduce resolution due to PSF...
    imageov = scipy.signal.fftconvolve(skyov, psfov, mode="same")
    return imageov, fovdet, halfdim, ipsov


def simulate_scenedata( _trials, 
                        skyscene_ov, psf_ov, psf_hdr, _cubename, osample,
                        _dithers, _x_dith, _y_dith,
                        ngroups, nint, frametime, filt,
                        outDir, tmpDir, utr, **kwargs):

	# sky is oversampled but convolved w/psf.  units: counts per second per oversampled pixel
	# fov is oversampled odd # of detector pixels
	# dim is a utility variable
    sky, fov, dim, ips_ov = adjustsizes(skyscene_ov, psf_ov, osample)
    del skyscene_ov
    del psf_ov
    # print "ips_ov.shape", ips_ov.shape
    cube = np.zeros((nint,int(fov),int(fov)), np.float64)

    # Simulated sky scene data
    for p in range(_trials):
        # print 'Starting trial', p
        #CALCULATE LOCATIONS OF 4 DITHERS WITH 15 MAS ERROR ON 256 X 11 ARRAY
        mean_d, sigma_d = 0, U.dither_stddev_as * osample/U.pixscl # units: oversampled pixels
        x_dith_error = np.random.normal(mean_d,sigma_d, _dithers)
        x_dith_error_r = [int(round(n, 0)) for n in x_dith_error]
        #Accumulate dither errors
        x_dith_error_accum = np.cumsum(x_dith_error_r)
        dither_xcenter = [a + b for a, b in zip(_x_dith, x_dith_error_accum)] 
  
        y_dith_error = np.random.normal(mean_d,sigma_d, _dithers)
        y_dith_error_r = [int(round(n, 0)) for n in y_dith_error]
        #Accumulate dither errors
        y_dith_error_accum = np.cumsum(y_dith_error_r)
        dither_ycenter = [a + b for a, b in zip(_y_dith, y_dith_error_accum)]
  
        if 0:
            print "\tPrinting commanded dither, accumulated error, final dither location for verification"
            print "  "
            print "\tcommanded X dither", _x_dith
            print "\tAccumulated X dither error", x_dith_error_accum
            print "\tdither_xcenter", dither_xcenter      
            print "  "
            print "\tcommanded Y dither", _y_dith
            print "\tAccumulated Y dither error", y_dith_error_accum
            print "\tdither_ycenter", dither_ycenter
            print "  "
  
        #POSITIONAL ERROR = DITHER + JITTER
        xjitter = range( _dithers)   #each of the 4 elements is an array of nint jitters
        yjitter = range( _dithers)   #one set per dither location
        
        for i in range( _dithers):
            xjitter[i], yjitter[i] = U.jitter(nint, osample)
            if 0:
                print '\t\tx jitter', xjitter[i]
                print '\t\ty jitter', yjitter[i]

        xjitter_array = np.array(xjitter)
        x = range( _dithers)

        yjitter_array = np.array(yjitter)      
        y = range( _dithers)

        total_pos_error_x = range( _dithers)
        total_pos_error_y = range( _dithers)

        # If one wishes to produced all the dithered datacubes change next line to ...range(_dithers)
        # _dithers number of values of the dither locations will need  to accompany this change.
        for i in range(1):
            x[i]= dither_xcenter[i] + xjitter_array[i]
            y[i]= dither_ycenter[i] + yjitter_array[i] 
            total_pos_error_x[i] = x[i] - _x_dith[i]
            total_pos_error_y[i] = y[i] - _y_dith[i]
            if 0:
                print " "
                print '\t\ttotal positional error in X', total_pos_error_x[i]
                print '\t\treal X pointing with dither and jitter', x[i]
                print " "
                print '\t\ttotal positional error in Y', total_pos_error_y[i]
                print '\t\treal Y pointing with dither and jitter', y[i] 
                print " "
                print '\t\tzip(x[i],y[i])',zip(x[i],y[i])

            for k,(ii,jj) in enumerate(zip(x[i],y[i])):

                ips_section = ips_ov[ii-dim*osample:ii+(dim+1)*osample,jj-dim*osample:jj+(dim+1)*osample]   
                skyscene_ov_ips_array = ips_section * sky
                
                skyscene_ov_ips_array_sh = U.apply_padding_image(skyscene_ov_ips_array,jj-dither_ycenter[i],ii-dither_xcenter[i], fov, osample)

                if 0:
                    print  "\t\tinfo", (int(dither_xcenter[i]-(dither_xcenter[i]//osample)*float(osample)), int(osample-(dither_xcenter[i]-(dither_xcenter[i]//osample)*osample)))
                    print  "\t\tinfo", (int(dither_ycenter[i]-(dither_ycenter[i]//osample)*float(osample)), int(osample-(dither_ycenter[i]-(dither_ycenter[i]//osample)*osample)))
                
                # magic pixel bookkeeping on the image
                im = np.pad(skyscene_ov_ips_array_sh,
                       [(int(dither_xcenter[i]-(dither_xcenter[i]//osample)*float(osample)), int(osample-(dither_xcenter[i]-(dither_xcenter[i]//osample)*osample))),
                        (int(dither_ycenter[i]-(dither_ycenter[i]//osample)*float(osample)), int(osample-(dither_ycenter[i]-(dither_ycenter[i]//osample)*osample)))],
                     mode='constant')

                #extra pixel gets added because of total padding of 11 ov pixels along rows and 11 ov pixels along columns
                #assuming that 11 ov pixels = 1 detector pixel

                rebinned_array_fovplusone = U.rebin(im, (osample,osample))
                rebinned_array = rebinned_array_fovplusone[0:fov,0:fov]
  
                ips_section_sh = U.apply_padding_ips(ips_section,jj-dither_ycenter[i],ii-dither_xcenter[i], fov, osample)
  
                # magic pixel bookkeeping on the ips array
                im_ips = np.pad(ips_section_sh, 
                       [(int(dither_xcenter[i]-(dither_xcenter[i]//osample)*float(osample)), int(osample-(dither_xcenter[i]-(dither_xcenter[i]//osample)*osample))),
                        (int(dither_ycenter[i]-(dither_ycenter[i]//osample)*float(osample)), int(osample-(dither_ycenter[i]-(dither_ycenter[i]//osample)*osample)))],
                     mode='constant', constant_values=(1,1)) 

                rebinned_ips_flat_fovplusone = U.rebin(im_ips, (osample,osample))/osample**2
                rebinned_ips_flat = rebinned_ips_flat_fovplusone[0:fov,0:fov]
                counts_array_persec = rebinned_array / rebinned_ips_flat


                ramp = U.create_ramp(counts_array_persec, fov, ngroups, utr)
                #fits.writeto('ramp.fits',ramp, clobber = True)

                pflat = U.get_flatfield((fov,fov))
                exposure = U.create_integration(ramp)
                exposure1 = (exposure - U.darkcurrent - U.background) * pflat

                cube[k,:,:] = exposure1     
                if 0:
                    print '\t\tmax pixel counts', cube[k,:,:].max()
                    print " "                   
  
            """
            print '\t_cubename', _cubename
            print '\tstr(p)', str(p), 
            print '\tstr(i)', str(i)
            """
            outfile = _cubename+str(p)+str(i)+".fits"
            print '\tcreating', _cubename+str(p)+str(i)+'.fits'

            (year, month, day, hour, minute, second, weekday, DOY, DST) =  time.gmtime()

            fitsobj = fits.HDUList()
            hdu = fits.PrimaryHDU(  )
            printhdr = hdu.header
     
  
            printhdr['INSTRUME']= 'NIRISS'
            printhdr['pixscl'] = U.pixscl, 'Pixel scale (arcsec/pixel)'
            printhdr['NRMNAME'] =  'G7S6', 'Tuthill Anand Beaulieu Lightsey'
            printhdr['NRM_X_A1'] =  0.00000, 'X (m) of NRM sub-ap 0 G7S6'          
            printhdr['NRM_Y_A1'] = -2.64000, 'Y (m) of NRM sub-ap 0'         
            printhdr['NRM_X_A2'] = -2.28631, 'X (m) of NRM sub-ap 1'          
            printhdr['NRM_Y_A2'] =  0.00000, 'Y (m) of NRM sub-ap 1'          
            printhdr['NRM_X_A3'] =  2.28631, 'X (m) of NRM sub-ap 2'          
            printhdr['NRM_Y_A3'] = -1.32000, 'Y (m) of NRM sub-ap 2'          
            printhdr['NRM_X_A4'] = -2.28631, 'X (m) of NRM sub-ap 3'          
            printhdr['NRM_Y_A4'] =  1.32000, 'Y (m) of NRM sub-ap 3'          
            printhdr['NRM_X_A5'] = -1.14315, 'X (m) of NRM sub-ap 4'          
            printhdr['NRM_Y_A5'] =  1.98000, 'Y (m) of NRM sub-ap 4'          
            printhdr['NRM_X_A6'] =  2.28631, 'X (m) of NRM sub-ap 5'          
            printhdr['NRM_Y_A6'] =  1.32000, 'Y (m) of NRM sub-ap 5'          
            printhdr['NRM_X_A7'] =  1.14315, 'X (m) of NRM sub-ap 6'          
            printhdr['NRM_Y_A7'] =  1.98000, 'Y (m) of NRM sub-ap 6'   
            printhdr['nframe'] = nint, 'number of frames'
            printhdr['ngroup'] = ngroups,'number of groups'  
            printhdr['framtime'] = frametime,'one(utr=1)/first-to-last(utr=0) (s)'
            printhdr['units'] = 'photoelectrons'
            printhdr['ffe_err'] = U.flat_sigma*100, '% Flat field error stddev'
            printhdr['jitter'] = U.jitter_stddev_as*1000, '1-axis jitter stddev mas'
            printhdr['dith_err'] = U.dither_stddev_as*1000, '1-axis dither placement stddev mas'
            printhdr['dithx%d'%i] = _x_dith[i]/osample, 'Commanded X dither (detpix in ipsarray)'
            printhdr['dithy%d'%i] = _y_dith[i]/osample, 'Commanded Y dither (detpix in ipsarray)'
            printhdr['dithx_r%d'%i] = dither_xcenter[i]/float(osample), 'Real X dither (detpix in ipsarray)'
            printhdr['dithy_r%d'%i] = dither_ycenter[i]/float(osample), 'Real Y dither (detpix in ipsarray)'
            printhdr['codesrc'] = 'make_scene.py', 'thatte@stsci.edu, anand@stsci.edu'
    
            # Append the header from psf_star.fits, likely created by WebbPSF
            printhdr.extend(psf_hdr, update=True)
  
            #Delete and over-write keyword values written by WebbPSF
            del printhdr['PLANE1']
            del printhdr['DET_SAMP']
            printhdr['oversamp']= osample, 'Oversampling factor for MFT'
            printhdr['AUTHOR'] = '%s@%s' % (os.getenv('USER'), os.getenv('HOST')), 'username@host for calculation'
            printhdr['DATE'] = '%4d-%02d-%02dT%02d:%02d:%02d' %  (year, month, day, hour, minute, second), 'Date of calculation'
  
            hdu.data = cube
            fitsobj.append( hdu )
            fitsobj.writeto(outDir+outfile, clobber = True)
            fitsobj.close()
            print "\nPeak pixel and total e- in each slice:"

        for i in range(cube.shape[0]):
            print i, " %.1e"%cube[i,:,:].max(), " %.1e"%cube[i,:,:].sum()
        print ""

        print "up-the-ramp %d"%utr, 
        print "\nTotal e- in cube:", "%.2e   "%cube.sum()
