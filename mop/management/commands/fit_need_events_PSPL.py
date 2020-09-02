from django.core.management.base import BaseCommand
from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target,TargetExtra
from django.db import transaction
from django.db import models
from astropy.time import Time
from mop.toolbox import fittools
from mop.brokers import gaia as gaia_mop
import json
import numpy as np
import datetime
import random
from django.db.models import Q

​
import time
import sys
import os
import datetime
import os



​
# TODO FIXME: this is where your fit code would go
def run_fit(target):
    print('Working on'+target.name)
    try:    
       if 'Gaia' in target.name:

           gaia_mop.update_gaia_errors(target)

       #Add photometry model

       
       if 'Microlensing' not in target.extra_fields['Classification']:
           alive = False

           extras = {'Alive':alive}
           target.save(extras = extras)
       
       else:


           datasets = ReducedDatum.objects.filter(target=target)
           time = [Time(i.timestamp).jd for i in datasets if i.data_type == 'photometry']
        
           phot = []
           for data in datasets:
               if data.data_type == 'photometry':
                  try:
                       phot.append([json.loads(data.value)['magnitude'],json.loads(data.value)['error'],json.loads(data.value)['filter']])
       
                  except:
                       # Weights == 1
                       phot.append([json.loads(data.value)['magnitude'],1,json.loads(data.value)['filter']])
           

           photometry = np.c_[time,phot]

           t0_fit,u0_fit,tE_fit,piEN_fit,piEE_fit,mag_source_fit,mag_blend_fit,mag_baseline_fit,cov,model = fittools.fit_PSPL_parallax(target.ra, target.dec, photometry, cores = options['cores'])


           return  t0_fit,u0_fit,tE_fit,piEN_fit,piEE_fit,mag_source_fit,mag_blend_fit,mag_baseline_fit,cov,model  
    except:
         pass  

class Command(BaseCommand):

    help = 'Fit events with PSPL and parallax, then ingest fit parameters in the db'
    
    def add_arguments(self, parser):

        parser.add_argument('--cores', help='Number of workers to use', default=os.cpu_count(), type=int)

    
    def handle(self, *args, **options):
    
        # Run until all objects which need processing have been processed
        while True:
            # One instance of our database model to process (if found)
            element = None
    ​
            # Select the first available un-claimed object for processing. We indicate
            # ownership of the job by advancing the timestamp to the current time. This
            # ensures that we don't have two workers running the same job. A beneficial
            # side effect of this implementation is that a job which crashes isn't retried
            # for another four hours, which limits the potential impact.
            #
            # The only time this system breaks down is if a single processing fit takes
            # more than four hours. We'll instruct Kubernetes that no data processing Pod
            # should run for that long. That'll protect us against that overrun scenario.
            #
            # The whole thing is wrapped in a database transaction to protect against
            # collisions by two workers. Very unlikely, but we're good software engineers
            # and will protect against that.
            with transaction.atomic():
                four_hours_ago = Time(datetime.datetime.utcnow() - datetime.timedelta(hours=4)).jd
                
                # https://docs.djangoproject.com/en/3.0/ref/models/querysets/#select-for-update

                queryset = Target.objects.select_for_update(skip_locked=True)
                queryset = queryset.filter(targetextra__in=Q(TargetExtra.objects.filter(key='last_fit', value__lte=fours_hours_ago) & TargetExtra.objects.filter(key='Alive', value=True)))
                element = queryset.first()
    ​
                # Claim the job as running by setting the last fit timestamp. This condition
                # has the beneficial side effect such that if a fit crashes, it won't be
                # re-run (retried) for another four hours. This limits the impact of broken
                # code on the cluster.
                last_fit = Time(datetime.datetime.utcnow()).jd
                extras = {'Last_fit':last_fit}
                element.save(extras = extras)
               
    ​
            # If there are no more objects left to process, then the job is finished.
            # Inform Kubernetes of this fact by exiting successfully.
            if element is None:
                print('Job is finished, no more objects left to process! Goodbye!')
                sys.exit(0)
    ​
            # Debugging information. Put something unique here, like "name of dataset"
            # or something useful like that.
            print(f'Processing dataset: {element.dataset_name}')
    ​
            # Now we know for sure we have an element to process, and we haven't locked
            # the database. We're free to process this for up to four hours.
            result = run_fit(element)
    ​
            if result is not None:
            
                t0_fit,u0_fit,tE_fit,piEN_fit,piEE_fit,mag_source_fit,mag_blend_fit,mag_baseline_fit,cov,model = result
        
                #Add photometry model
                           
                model_time = datetime.datetime.strptime('2018-06-29 08:15:27.243860', '%Y-%m-%d %H:%M:%S.%f')
                data = {'lc_model_time': model.lightcurve_magnitude[:,0].tolist(),
                'lc_model_magnitude': model.lightcurve_magnitude[:,1].tolist()
                        }
                existing_model =   ReducedDatum.objects.filter(source_name='MOP',data_type='lc_model',
                                                              timestamp=model_time,source_location=target.name)

                                                                
                if existing_model.count() == 0:     
                    rd, created = ReducedDatum.objects.get_or_create(
                                                                        timestamp=model_time,
                                                                        value=json.dumps(data),
                                                                        source_name='MOP',
                                                                        source_location=target.name,
                                                                        data_type='lc_model',
                                                                        target=target)                  

                    rd.save()

                else:
                    rd, created = ReducedDatum.objects.update_or_create(
                                                                        timestamp=existing_model[0].timestamp,
                                                                        value=existing_model[0].value,
                                                                        source_name='MOP',
                                                                        source_location=target.name,
                                                                        data_type='lc_model',
                                                                        target=target,
                                                                        defaults={'value':json.dumps(data)})                  

                    rd.save()


                time_now = Time(datetime.datetime.now()).jd
                how_many_tE = (time_now-t0_fit)/tE_fit


                if how_many_tE>2:

                   alive = False

                else:

                   alive = True

                last_fit = Time(datetime.datetime.utcnow()).jd


                extras = {'Alive':alive, 't0':np.around(t0_fit,3),'u0':np.around(u0_fit,5),'tE':np.around(tE_fit,3),
                 'piEN':np.around(piEN_fit,5),'piEE':np.around(piEE_fit,5),
                 'Source_magnitude':np.around(mag_source_fit,3),
                 'Blend_magnitude':np.around(mag_blend_fit,3),
                 'Baseline_magnitude':np.around(mag_baseline_fit,3),
                 'Fit_covariance':json.dumps(cov.tolist()),
                 'Last_fit':last_fit}
                target.save(extras = extras)
​
if __name__ == '__main__':
    main()
