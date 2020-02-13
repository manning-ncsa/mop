from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from tom_alerts.alerts import GenericBroker, GenericQueryForm
from django import forms
from tom_targets.models import Target
from tom_observations import facility
from tom_dataproducts.models import ReducedDatum

from astropy.coordinates import SkyCoord
import astropy.units as unit
import urllib
import os
import numpy as np
import json
from astropy.time import Time, TimezoneInfo


BROKER_URL = 'https://www.massey.ac.nz/~iabond/moa/'
photometry = "https://www.massey.ac.nz/~iabond/moa/alert2019/fetchtxt.php?path=moa/ephot/"

class MOAQueryForm(GenericQueryForm):
    target_name = forms.CharField(required=False)
    cone = forms.CharField(
        required=False,
        label='Cone Search',
        help_text='RA,Dec,radius in degrees'
    )

    def clean(self):
        if len(self.cleaned_data['target_name']) == 0 and \
                        len(self.cleaned_data['cone']) == 0:
            raise forms.ValidationError(
                "Please enter either a target name or cone search parameters"
                )

class MOABroker(GenericBroker):
    name = 'MOA'
    form = MOAQueryForm

    def add_arguments(self, parser):
        parser.add_argument('years', help='years you want to harvest, spearted by ,')

    def fetch_alerts(self, moa_files_directories, years = []):
        
       

        #ingest the TOM db
        list_of_targets = []
        self.event_dictionnary = {}
        for year in years:
            url_file_path = os.path.join(BROKER_URL+'alert'+str(year)+'/index.dat' )
            events = urllib.request.urlopen(url_file_path).readlines()

            for event in events[0:]:
                   
                   event = event.decode("utf-8").split(' ')
                   name = 'MOA-'+event[0]
                   #Create or load
                   self.event_dictionnary[name] = [event[1],event[-2],event[-1]]
                   coords = [float(event[2]),float(event[3])]
                   cible = SkyCoord(coords[0],coords[1],unit="deg")
                   target, created = Target.objects.get_or_create(name=name,ra=cible.ra.degree,dec=cible.dec.degree,
                                   type='SIDEREAL',epoch=2000)
                   if created:

                       target.save()
                   
                   list_of_targets.append(target)


        return list_of_targets


    def find_and_ingest_photometry(self, targets):

        
        
        for target in targets:
            
            year = target.name.split('-')[1]
            event = self.event_dictionnary[target.name][0]


            url_file_path = os.path.join(BROKER_URL+'alert'+str(year)+'/fetchtxt.php?path=moa/ephot/phot-'+event+'.dat' )
            lines = urllib.request.urlopen(url_file_path).readlines()

            jd = []
            mags = []
            emags = []

            for line in lines:
 
                line = line.decode("utf-8").split("  ")
                try:
                    
                    phot = [i for i in line if i!='']
                    tot_flux = float(self.event_dictionnary[target.name][2])+float(phot[1])
                    mag = float(self.event_dictionnary[target.name][1])-2.5*np.log10(tot_flux)
                    emag = float(phot[2])/tot_flux*2.5/np.log(10)
                    if (np.isfinite(mag)) & (emag>0) & (float(phot[0])>2451544.50000): 
                        jd.append(float(phot[0]))
                        mags.append(mag)
                        emags.append(emag)
                    
                except:
                    pass    


            photometry = np.c_[jd,mags,emags]
           #photometry = photometry[photometry[:,0].argsort()[::-1],] #going backward to save time on ingestion
            



            for index,point in enumerate(photometry):
                try:
                    jd = Time(point[0], format='jd', scale='utc')
                    jd.to_datetime(timezone=TimezoneInfo())
                    data = {   'magnitude': point[1],
                           'filter': 'MOA_R',
                           'error': point[2]
                       }
                    rd, created = ReducedDatum.objects.get_or_create(
                    timestamp=jd.to_datetime(timezone=TimezoneInfo()),
                    value=json.dumps(data),
                    source_name=target.name,
                    source_location='MOA Alerts',
                    data_type='photometry',
                    target=target)
               
                    if created:

                        rd.save()

                    else:
                        # photometry already there (I hope!)
                        break
                except:
                    import pdb; pdb.set_trace()

    def to_generic_alert(self, alert):
        pass
  