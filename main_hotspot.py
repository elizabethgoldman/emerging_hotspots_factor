import emerging_hotspot_factor
import arcpy
import os

#Set up loss, area, and TCD mosaics. Insert a remap on TCD to 31-101 = 1 and <30 = NoData.
#Insert an arithmetic function on loss, multiply TCD mosaic with loss mosaic.

# set directories for variables
country = r'S:\ehs\africa_test.shp'
country_int = r'S:\ehs\africa_test_int.shp'
tile_grid = r'S:\lossdata_footprint.shp'
lossyearmosaic = r'S:\ehs\hs_mosaics.gdb\loss17'
hansenareamosaic = r'S:\ehs\hs_mosaics.gdb\area'
tcd_masks = r'S:\tcd_masks'
snap_results = r'S:\ehs\ehs_files\test_agg.tif'
remap_table = r'S:\ehs\ehs_files\hs_function_table.dbf'
#on first set up, edit the function and make sure remap table location is pointing to correct directory
year_remap_function = r'S:\ehs\ehs_files\remap_loss_year.rft.xml'


current_dir = os.path.dirname(os.path.realpath(__file__))
datadir = os.path.join(current_dir, "data")
if not os.path.exists(current_dir + "\data"):
    os.makedirs(current_dir + "\data")

arcpy.env.workspace = datadir
arcpy.env.overwriteOutput = True
fields = ["ISO"]

with arcpy.da.SearchCursor(country, fields) as cursor:
        for row in cursor:
            iso = row[0]
            print("running code for {}".format(iso))
            where = '"ISO" = ' + "'{}'".format(iso)
            country_selection = "country_selection"
            country_shapefile = os.path.join(datadir, "country_shapefile.shp")
            arcpy.Select_analysis(country, country_shapefile, where)

            emerging_hotspot_factor.emerging_hs_points(tile_grid, lossyearmosaic, hansenareamosaic, country_shapefile,
                                                       country_int, datadir, iso, remap_table, year_remap_function,
                                                       snap_results, tcd_masks)
