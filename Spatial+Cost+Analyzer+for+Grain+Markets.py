
# coding: utf-8

# # Optimized-Profit Route Matrix
# 
# Author: Travis Fried
# Date: 5/9/17
# Class: Geocomputing
# Note: Run in Python 3

# In[ ]:

import fiona
from pprint import pprint
import math
import csv
import utm
import googlemaps
import time
import requests


# ### Functions to parse and extract .shp data for Corn IDs (origin) and market elevators (destination)
# While the algorithm is set up to look at unique data for Dodge and Swift county, future versions will be able to accept all properly formatted O-D shp data. Sadly, I didn't standardize the filenames. In the future, O-D filenames (in this case, corn points and market locals) would have to be formatted a certain way in order for the metho to function properly. These filenames reflect the files enclosed in the folder

# In[ ]:

#extract corn point data (shp) to local list/dict
def extractCornPointData(shp):
    corn_data = []

    with fiona.open(shp) as shp_f:
        for cPoint in shp_f:
            corn_data.append({'CornID': cPoint['id'], 'XYcoordinates': cPoint['geometry']['coordinates'], 
                              'corn_bu': cPoint['properties']['Corn_bu']})
            
    return corn_data


# In[ ]:

#INSERT FILE NAME HERE
#'Swift_Corn_2014_join_2.shp'
#'Dodge_2014_Corn_Points.shp'
corn_data = extractCornPointData('Swift_Corn_2014_join_2.shp')


# In[ ]:

#extract elevator market data (shp) to local list/dict
def extractElevatorPointData(shp):
    elevator_data = []

    with fiona.open(shp) as shp_f:
        for ePoint in shp_f:
            print(type(ePoint['geometry']['coordinates'][0]))
            elevator_data.append({'city': ePoint['properties']['City'], 'el_name': ePoint['properties']['Company_Na'], 
                                  'XYcoordinates': ePoint['geometry']['coordinates'],
                                  'type': ePoint['properties']['type'],
                                  'spot_price':ePoint['properties']['Spot'], 'spot_basis':ePoint['properties']['Spot_K'],
                                  'oct17_price':ePoint['properties']['price_10_1'], 'oct17_basis':ePoint['properties']['basis_10_1']})

    #DATA CLEANING CONDITIONALS GO HERE
    for ePoint in elevator_data:
        if ePoint['el_name'] == 'ADM Burr Elevator':
            ePoint['oct17_price'] = 3.19
        if ePoint['el_name'] == 'ADM Benson Quinn':
            ePoint['spot_basis'] = '-53K'
        if ePoint['oct17_basis'] == '0 Z':
            ePoint['oct17_basis'] = None
        #Turn off Marshall Elevator data (swift county) (taken from different source; affects data greatly)
        if ePoint['city'] == 'Marshall':
            ePoint['spot_price'] = None
        if "\xa0" in ePoint['el_name']:
            malbit= "\xa0"
            ePoint['el_name'] = ePoint['el_name'].replace(malbit,'')
        if ePoint['city'] == None:
            ePoint['city'] = "NA" 
            
    return elevator_data


# In[ ]:

#INSERT FILE NAME HERE
#'Elevators_prj_final.shp' (NAME OF SWIFT ELEVATOR SHP)
#Elevators_dodge_UTM15.shp
elevator_data = extractElevatorPointData('Elevators_prj_final.shp')


# ### Functions to calculate distance using 3 different methods
# While I attempted to use Google API, the number of requests I was making exceeded Google's free trial. To fix this, I used OSM's API, which calls an HTML service. I had to convert UTM coordinates to WGS84 and convert the HTML to JSON. Every once in a 10 thousand iterations, the function would throw a JSON reading error. I remedied this by calculating the manhattan distance instead. This debug is in the main function; however, future versions would call the calcManhattanDistance function in the except clause of the calcOSMDistance function.

# In[ ]:

#UTM to WGS84 convesion for OSRM distance calculator
def UTMconversion(UTM_XY):
    WGS84_XY = utm.to_latlon(UTM_XY[0], UTM_XY[1], 15, 'N')
    return WGS84_XY


# In[ ]:

#Calculate Manhattan distance between corn,i and elevator,j (returns miles)
def calcManhattanDistance(XYcorn, XYelevator):
    cMile = 1609.344
    mDistance = (abs((XYcorn[0] - XYelevator[0])) + abs((XYcorn[1] - XYelevator[1]))) / cMile
    return mDistance


# In[ ]:

#Calculate Google API distance between corn,i and elevator,j (returns miles)
#No longer used 
def calcGoogleDistance(O_XY, D_XY):
    
    time.sleep(1)
    gmaps = googlemaps.Client(key='AIzaSyDqmvgLGbsZ_o-DbbAW5Sb_yO-NlBPKP5k')
    matrix = gmaps.distance_matrix(UTMconversion(O_XY), UTMconversion(D_XY), units="imperial")
    distanceMiles = matrix['rows'][0]['elements'][0]['distance']['value'] * 0.000621371
    return distanceMiles


# In[ ]:

#Calculate OSRM distance between corn,i and elevator,j (returns miles) 
def calcOSMDistance(O_XY, D_XY):
    
    #Initialize function vars
    cMile = 1609.344
    WGS84_O_XY = UTMconversion(O_XY)
    WGS84_D_XY = UTMconversion(D_XY)
    URL = 'http://router.project-osrm.org/route/v1/driving/'
    
    #Request OSRM HTTP
    r = requests.get(URL+str(WGS84_O_XY[1])+","+str(WGS84_O_XY[0])+";"+
                     str(WGS84_D_XY[1])+","+str(WGS84_D_XY[0]))
    
    #Convert request to JSON and calculate distance
    try:
        matrix = r.json()
        distanceMiles = matrix['routes'][0]['distance'] / cMile
        return distanceMiles
    
    #Catch all exceptions and return NONE if error
    except:
        print(r.text)
        pass


# ### Optimized profit calculator

# In[ ]:

#Convert annual county corn production to month-specific output
#State-level 2014 monthly market share taken from USDA
def bushelToMonthlyTons(cornBU, month):
    
    #Convert bushels to tons (bushel = 56lbs)
    cornTons = (cornBU * 56) / 2000
    
    #APRIL
    if month == True:
        cornTons = cornTons * 0.07
        return cornTons
    #OCTOBER
    else:
        cornTons = cornTons * 0.09
        return cornTons
    


# In[ ]:

def calcProfitPerTonMile(distance, cornBU, price, basis, month):

    #Calculate cost per Ton-Mile
    def calcCostPerTonMile(distance, cornBU, month):
        #Mitra et. al. (2007) give the breakdowns of truck types and costs used in corn trucking
        #values have NOT been updated to reflect current fuel costs
    
        #2A_SU: 2-axle single unit, 3A_SU: 3-axle single unit, 4A_SU: 4-axle single unit, 3_S2: Semi
        #Assumes avg speed = 60 mph
        #calculates for there and back
        
        #Initialize local vars
        base = 0
        truck_dict = {'2A_SU':{'proportion':9.25,'costPerTonMile':0.052,'payloadTons': 11.25,'tareTons':4.75},
                      '3A_SU':{'proportion':35.25,'costPerTonMile':0.041,'payloadTons': 14.8,'tareTons':8.2},
                      '4A_SU':{'proportion':15.25, 'costPerTonMile':0.029,'payloadTons':21.25,'tareTons':8.75},
                      '3_S2':{'proportion':44.25, 'costPerTonMile':0.029,'payloadTons':26.6, 'tareTons':13.4}}
        cornTons = bushelToMonthlyTons(cornBU, month)
    

        #Iterate through truck data
        for t in truck_dict:
            trucks = truck_dict[t]
    
            #Estimate number of payloads, trucks, and GVW
            payloads = cornTons/trucks['payloadTons']
            numberOfTrucks = int(cornTons/trucks['payloadTons']) + 1
            GVW =trucks['payloadTons'] + trucks['tareTons']
    
            #Calculate the sum of cost: loaded there, unloaded back  
            trucks_cost = ((distance * trucks['costPerTonMile'] * (cornTons + (numberOfTrucks * trucks['tareTons']))) +
                           (distance * trucks['costPerTonMile'] * numberOfTrucks * trucks['tareTons'])) / trucks['proportion']
            base += trucks_cost
    
        return base
    
    #Calculate income per bushel
    #Basis function is basis,t = CashPrice,t - FuturePrice,t (t= contract time) (Baldwin n.d.)
    def calcIncomePerBU(price , basis, cornBU, month):
        
        #If month is spot month (True), use spot price
        if month == True:
            #April income
            income = (cornBU * 0.07) * price
            
        #Else, use price - basis price
        else:
            #October income
            futures = price - (float(basis[0:3])/100)
            income = (cornBU * 0.09) * futures
    
        return income

    #Calculate and return profit as float currency
    profit = calcIncomePerBU(price, basis, cornBU, month) - calcCostPerTonMile(distance, cornBU, month)
    return float("%.2f" % profit)


# ### Main Function
# This segment compiles distance and cost calculations collects unique O-D pairs of max profit for both apr (spot = True) and oct (else). The output is two csv's properly formatted to run with ease through ESRI's network analyst. The first CSV contains origin information (unique Corn IDs to optimized market) with information on location, distance, amount of bushels (specific to the month and ID), and profit. The second CSV contains a list of all unique destinations and their location. The OD matrix is loaded into the nearest facility vehicle routing problem as 'Facilities' while the D locator is loaded as 'Incidents.'

# In[ ]:

#Create new dict/list to include distance between corn, i and best-profit elevator
def findOptimalMarkets(corn_dict, elevator_dict, spot = True):
    
    #Initialize counting and empty list vars
    ccount = 0
    cornMarkets = []
    destinations = []
        
    #Iterate through corn dictionary and intialize loop counting variables
    for c in range(len(corn_dict)):
        corn = corn_dict[c]
        base = 0
        ecount = 0
        
        #Main status report
        print("writing corn #", ccount, "out of ", len(corn_dict))
        print("")
        ccount += 1
        
        #Iterate through elevator dictionary 
        for e in range(len(elevator_dict)):
            elevator = elevator_dict[e]
            
            #Create unique O-D name for later GIS spatial join
            OD_name = corn['CornID'] + " - " + elevator['el_name'] + "(" + elevator['city'] + ")"
            
            #Secondary status report (for debugging)
            #print("elevator#", ecount, "out of", len(elevator_dict))
            #ecount+= 1
            
            #Remove empty market price values from analysis
            if elevator['spot_price'] == None or elevator['oct17_price'] == None or elevator['oct17_basis'] == None:
                continue
            else:
                
                #Calculate OD distance, prioritizing OSRM
                distance = calcOSMDistance(corn['XYcoordinates'], elevator['XYcoordinates'])
                
                #If OSRM fails (returns None), calculate Manahattan 
                #future versions will run this in calcOSMDistance() function
                if distance == None:
                    distance = calcManhattanDistance(corn['XYcoordinates'], elevator['XYcoordinates'])
                    #Print and log when OSRM is NOT used
                    print("ROUTING DISTANCE ERROR--Manhattan used for: CornID", corn['CornID'] + ";", "Elevator", (elevator['el_name']+'('+elevator['city']+')'))
                
                #APRIL
                if spot == True: 
                    
                    #calculate April profit
                    profit = calcProfitPerTonMile(distance, corn['corn_bu'], elevator['spot_price'], elevator['spot_basis'], spot)
                    
                    #Find maximum April(spot) profit
                    if profit > base:
                        base = profit
                        base_dict = {'orignID':corn['CornID'], 'cornBU_tot':corn['corn_bu'], 'cornTons_Apr':bushelToMonthlyTons(corn['corn_bu'], spot), 'originXY':corn['XYcoordinates'],
                                     'destinationName':(elevator['el_name']+'('+elevator['city']+')'), 'destinationCity': elevator['city'],'type': elevator['type'],
                                     'destinationXY': elevator['XYcoordinates'], 'price': elevator['spot_price'], 'basis': elevator['spot_basis'],
                                     'profit': base, 'mDistance': distance, 'OD_name': OD_name}
                
                #OCTOBER
                else:
                    
                    #calculate Oct profit
                    profit = calcProfitPerTonMile(distance, corn['corn_bu'], elevator['oct17_price'], elevator['oct17_basis'], spot)
                
                    #Find maximum Oct profit
                    if profit > base:
                        base = profit
                        #FOR FUTURE VERSIONS, PERHAPS REPLACE elevator['oct17_price'] WITH elevator['spot_price']... I think this may be due to misconceptions of basis
                        base_dict = {'orignID':corn['CornID'], 'cornBU_tot':corn['corn_bu'], 'cornTons_Oct':bushelToMonthlyTons(corn['corn_bu'], spot), 'originXY':corn['XYcoordinates'],
                                     'destinationName':(elevator['el_name']+'('+elevator['city']+')'), 'destinationCity':elevator['city'],'type':elevator['type'],
                                     'destinationXY':elevator['XYcoordinates'], 'price':elevator['oct17_price'], 'basis': elevator['oct17_basis'],
                                     'profit': base, 'mDistance': distance,'OD_name': OD_name}
                
                #At end of elevator iteration, append Apr or Oct max profits to local dictionary
                if e >= len(elevator_dict)-1:
                    cornMarkets.append(base_dict)
                    
             
        #At end of corn iteration, write csv files    
        if c >= len(corn_dict)-1:
            
            #Write O-D data csv
            with open('/Users/travisfried/Desktop/Grain CSV/Swift_OD_October.csv', 'w') as fh:
                w = csv.DictWriter(fh,cornMarkets[0].keys())
                w.writeheader()
                w.writerows(cornMarkets)
            
            #Find and append unique destinations to local list
            for e in cornMarkets:
                if destinations == []:
                    destinations.append({'destinationName':e['destinationName'], 'destinationCity':e['destinationCity'],'type':e['type'],
                                         'destinationXY':e['destinationXY']})
                else:
                    if not any(d['destinationName'] == e['destinationName'] for d in destinations):
                            destinations.append({'destinationName':e['destinationName'], 'destinationCity':e['destinationCity'],'type':e['type'],
                                                 'destinationXY':e['destinationXY']})
                            
            #Write destinations to locator csv                 
            with open('/Users/travisfried/Desktop/Grain CSV/Swift_D_October.csv', 'w') as fh:
                w = csv.DictWriter(fh,destinations[0].keys())
                w.writeheader()
                w.writerows(destinations)


# In[ ]:

#RUN FUNCTION
findOptimalMarkets(corn_data,elevator_data, spot = False)
print("")
print("done!")


# Made a mistake and wrote long/lat as tuples and not independent fields (not suitable for Arc mapping). This means I have to rewrite csv's. I made the additional conversion of UTM coordinates to lat/lon (esri's street edge file is in web merc). Re-writing and re-running main body of code would take to long; however, this should be done for later versions.

# In[ ]:

def rewrite(file, OD = True):
    
    #initialize local dict
    rewrite = [] 
    
    #if OD file
    if OD == True: 
        #read old
        with open('/Users/travisfried/Desktop/Grain CSV/'+ file) as fh:
            r = csv.DictReader(fh)
            for row in r:
                XY = row['originXY']
                #convert to UTM (had to convert a str tuple to float values)
                WGS84_XY = UTMconversion([float(XY[1:XY.index(',')]), float(XY[XY.index(" ") + 1: len(XY) - 2])])
                #Add to new dict
                row.update({"Y": WGS84_XY[0], "X": WGS84_XY[1]})
                rewrite.append(row)
                
        #write new        
        with open ('/Users/travisfried/Desktop/Grain CSV/' + file[:len(file)-4] + '_WGS84geocode.csv', 'w') as fh:
            w = csv.DictWriter(fh,rewrite[0].keys())
            w.writeheader()
            w.writerows(rewrite)
            
    #If destination locator file        
    else:
        #read old
        with open('/Users/travisfried/Desktop/Grain CSV/'+ file) as fh:
            r = csv.DictReader(fh)
            for row in r:
                XY = row['destinationXY']
                #convert to UTM (had to convert a str tuple to float values)
                WGS84_XY = UTMconversion([float(XY[1:XY.index(',')]), float(XY[XY.index(" ") + 1: len(XY) - 2])])
                #Add to new dict
                row.update({"Y": WGS84_XY[0], "X": WGS84_XY[1]})
                rewrite.append(row)
                
        #write new    
        with open ('/Users/travisfried/Desktop/Grain CSV/' + file[:len(file)-4] + '_WGS84geocode.csv', 'w') as fh:
            w = csv.DictWriter(fh,rewrite[0].keys())
            w.writeheader()
            w.writerows(rewrite)


# In[ ]:

#Enter ALL newly created CSV names here
rewrite('Swift_OD_October.csv')
print("Done!")

