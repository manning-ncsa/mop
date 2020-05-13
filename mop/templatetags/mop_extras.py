import json

from django import template
from django.conf import settings
from django.core.paginator import Paginator
from datetime import datetime

from plotly import offline
import plotly.graph_objs as go

from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_dataproducts.processors.data_serializers import SpectrumSerializer

from astropy.time import Time
register = template.Library()



@register.inclusion_tag('tom_dataproducts/partials/photometry_for_target.html')
def mop_photometry(target):
    """
    Renders a photometric plot for a target.
    This templatetag requires all ``ReducedDatum`` objects with a data_type of ``photometry`` to be structured with the
    following keys in the JSON representation: magnitude, error, filter
    """
    photometry_data = {}
    for datum in ReducedDatum.objects.filter(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]):
        values = json.loads(datum.value)
        try:
            if  values['error']<0.25:
                photometry_data.setdefault(values['filter'], {})
                photometry_data[values['filter']].setdefault('time', []).append(Time(datum.timestamp).jd-2450000)
                photometry_data[values['filter']].setdefault('magnitude', []).append(values.get('magnitude'))
                photometry_data[values['filter']].setdefault('error', []).append(values.get('error'))

        except:
                
                photometry_data.setdefault(values['filter'], {})
                photometry_data[values['filter']].setdefault('time', []).append(Time(datum.timestamp).jd-2450000)
                photometry_data[values['filter']].setdefault('magnitude', []).append(values.get('magnitude'))
                photometry_data[values['filter']].setdefault('error', []).append(values.get('error'))
    plot_data = [
        go.Scatter(
            x=filter_values['time'],
            y=filter_values['magnitude'], mode='markers',
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values['error'],
                visible=True
            )
        ) for filter_name, filter_values in photometry_data.items()]
   


    layout = go.Layout(
        yaxis=dict(autorange='reversed'),
        height=600,
        width=700,
             
    )
   
    fig = go.Figure(data=plot_data, layout=layout)
    current_time =  Time.now().jd-2450000
    fig.add_shape(
        # Line Vertical
        dict(
             type="line",
             x0=current_time,
             y0=0,
             x1=current_time,
             y1=1,
             yref='paper',
             layer='below',
             line=dict(
                 color="Black",
                 width=1,
                 dash='dash',
                 )

    ))
    fig.update_layout(

    annotations=[
        dict(
             x=current_time,
             xanchor="left",
             y=0.05,
             yref="paper",
             text="JD now",
             showarrow=False,
             textangle=-90,)
    ]
    )
    return {
        'target': target,
        'plot': offline.plot(fig, output_type='div', show_link=False)
    }


