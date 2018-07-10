import fiona
from shapely.geometry import shape
import arcpy
import os
import subprocess
import arcgisscripting
import glob


gp = arcgisscripting.create(9.3)


def scratch_folder(datadir):
    scratch_workspace = os.path.join(datadir, "scratch")
    if not os.path.exists(scratch_workspace):
        os.mkdir(scratch_workspace)
    return scratch_workspace


def results_gdb(datadir, gdb_name):
    gdb = "{}.gdb".format(gdb_name)
    results_gdb = os.path.join(datadir, gdb)
    if not os.path.exists(results_gdb):
        arcpy.CreateFileGDB_management(datadir, gdb)
    return results_gdb


def select_tiles(country, footprint):
    tile_list = []
    with fiona.open(footprint, 'r') as grid:
        with fiona.open(country, 'r') as country:

            # compare each feature in dataset 1 and 2
            for g in grid:
                tileid = g['properties']['Name'][-8:]
                for i in country:
                    # print tile ID if geometry intersects
                    if shape(g['geometry']).intersects(shape(i['geometry'])):
                        tile_list.append(tileid)
                    else:
                        pass
    return tile_list


def clipped_mask_list(tile_list, country_shapefile, datadir, tcd_masks):
    clipped_list = []
    for tileid in tile_list:
        mask_tile = os.path.join(tcd_masks, tileid + ".shp")
        clipped_mask = tileid + "_clip.shp"
        clipped_mask_path = os.path.join(datadir, clipped_mask)
        arcpy.Clip_analysis(mask_tile, country_shapefile, clipped_mask_path)
        clipped_list.append(clipped_mask_path)
    return clipped_list

def erase_mask_list(tile_list, country_shapefile, datadir):
    clipped_list = []
    for tileid in tile_list:
        mask_tile = os.path.join(r"s:\tcd_masks", tileid + ".shp")
        clipped_mask = tileid + "_clip.shp"
        clipped_mask_path = os.path.join(datadir, clipped_mask)
        arcpy.Erase_analysis(mask_tile, country_shapefile, clipped_mask_path)
        clipped_list.append(clipped_mask_path)
    return clipped_list


def merge_clipped_masks(clipped_list, datadir, iso):
    merged_masks = os.path.join(datadir, iso + "_tcd_merged_mask")
    arcpy.Merge_management(clipped_list, merged_masks)
    return merged_masks


def merge_polygon_simplify(merged_masks, datadir, iso):
    simp_masks = os.path.join(datadir, iso + "_tcd_merged_mask_simp")
    arcpy.SimplifyPolygon_cartography(merged_masks, simp_masks, "BEND_SIMPLIFY", "1 Meters", "100 Hectares")


    #simp_masks_dis = os.path.join(datadir, iso + "_tcd_merged_mask_simp_dis")
    #arcpy.Dissolve_management(simp_masks, simp_masks_dis, dissolve_field="", statistics_fields="", multi_part="MULTI_PART, unsplit_lines="DISSOLVE_LINES")

    #simp_masks_dis_int = os.path.join(datadir, iso + "_tcd_merged_mask_simp_dis_int")
    #arcpy.Intersect_analysis([simp_masks_dis, tile_grid],simp_masks_dis_int)

    return simp_masks


def extract_loss(scratch, lossyearmosaic, country_shapefile_int, iso, scratch_gdb):
    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = scratch_gdb
    arcpy.env.scratchWorkspace = scratch

    mosaic_name = iso + "_extract"
    sr = 4326
    iso_loss_mosaic = arcpy.CreateMosaicDataset_management(scratch_gdb, mosaic_name, sr)

    fields = ['ISO', 'SHAPE@']
    shapecount = 0
    with arcpy.da.SearchCursor(country_shapefile_int, fields) as cursor:
        for row in cursor:
            shapecount += 1
            iso_row = row[0]
            geometry = row[1]
            if iso_row == iso:
                country_loss_30tcd = arcpy.sa.ExtractByMask(lossyearmosaic, geometry)
                extracted_folder = os.path.join(scratch, "extracted_tifs")
                if not os.path.exists(extracted_folder):
                    os.mkdir(extracted_folder)
                extracted_tif = os.path.join(extracted_folder, "{0}_{1}.tif".format(iso, shapecount))
                country_loss_30tcd.save(extracted_tif)

                extracted_tif_nd = extracted_tif.replace(".tif", "_nd.tif")
                cmd = ["gdal_translate", "-a_nodata", "0", extracted_tif, extracted_tif_nd]
                subprocess.check_call(cmd)

    # arc having trouble deleting pre-nodata files, so just adding nd to mosaic
    nd_tifs = glob.glob(os.path.join(extracted_folder, "{}*nd*".format(iso)))
    for tif in nd_tifs:
        arcpy.AddRastersToMosaicDataset_management(iso_loss_mosaic, "Raster Dataset", tif)

    return iso_loss_mosaic


def update_remap_table(remap_table, shortyear):
    fields = ["from_", "to"]

    with arcpy.da.UpdateCursor(remap_table, fields) as cursor:
        for row in cursor:

            remap_from = row[0]

            if remap_from == shortyear:
                row[1] = 1
            else:
                row[1] = 0

            cursor.updateRow(row)


def update_reclass_function(lossyearmosaic, year_remap_function):
    print('removing function')
    arcpy.EditRasterFunction_management(lossyearmosaic, "EDIT_MOSAIC_DATASET", "REMOVE", year_remap_function)
    print('inserting function')
    arcpy.EditRasterFunction_management(lossyearmosaic, "EDIT_MOSAIC_DATASET", "INSERT", year_remap_function)


def create_mosaic(country_loss_30tcd, scratch_gdb):

    out_cs = arcpy.SpatialReference(4326)
    mosaic_name = "mosaic_country_loss_30tcd"
    mosaic_path = os.path.join(scratch_gdb, mosaic_name)

    arcpy.CreateMosaicDataset_management(scratch_gdb, mosaic_name, out_cs)

    arcpy.AddRastersToMosaicDataset_management(mosaic_path, "Raster Dataset", country_loss_30tcd)

    return os.path.join(scratch_gdb, mosaic_name)


def aggregate(scratch, iso, mosaic_country_loss_30tcd, snap_results):
    arcpy.env.snapRaster = snap_results
    agg_out = os.path.join(scratch, iso + "_aggregate.tif")
    cell_factor = 80
    loss_aggregate = arcpy.gp.Aggregate_sa(mosaic_country_loss_30tcd, agg_out, cell_factor, "SUM", "TRUNCATE", "DATA")
    return loss_aggregate


def raster_to_point(scratch, iso, loss_aggregate, short_year):
    temp_points = os.path.join(scratch, iso + "_{}_temp_points".format(short_year))

    arcpy.RasterToPoint_conversion(loss_aggregate, temp_points, "Value")

    return temp_points


def add_date (temp_points, short_year):
    arcpy.AddField_management(temp_points, "date", "DATE")
    date_for_points = "\"01/01/{}\"".format(2000 + short_year)
    arcpy.CalculateField_management(temp_points, "date", date_for_points, "PYTHON")


def create_append_fc(geodatabase, iso, temp_points, short_year):
    all_points = os.path.join(geodatabase, iso + "_all_points")
    sr = 32662  # EPSG code for Plate Carree

    if arcpy.Exists(all_points):
        if short_year == 1:
            arcpy.Delete_management(all_points)
            print("making and appending {}".format(temp_points))
            arcpy.CreateFeatureclass_management(geodatabase, iso + "_all_points", "POINT", template=temp_points,
                                                spatial_reference=sr)
            arcpy.Append_management(temp_points, all_points)
        else:
            print("     appending points")
            arcpy.Append_management(temp_points, all_points)
    else:
        print("making and appending {}".format(temp_points))
        arcpy.CreateFeatureclass_management(geodatabase, iso + "_all_points", "POINT", template=temp_points,
                                            spatial_reference=sr)
        arcpy.Append_management(temp_points, all_points)

    arcpy.Delete_management(temp_points)
    return all_points



def create_space_time_cube(all_points, geodatabase, iso):
    out_cube = os.path.join(geodatabase, iso + "_cube.nc")
    arcpy.stpm.CreateSpaceTimeCube(all_points, out_cube, "date", None, "1 Years", "START_TIME", None,
                                   "2226.3898 Meters", "grid_code SUM ZEROS")
    return out_cube

def create_hot_spots(outcube, results_gdb, iso, simplified_mask, datadir):

    emerging_hotspot_result = os.path.join(results_gdb, iso + "_ehs")
    arcpy.EmergingHotSpotAnalysis_stpm(outcube, "GRID_CODE_SUM_ZEROS", emerging_hotspot_result,
                                       None, 1, simplified_mask)

    log = os.path.join(datadir, iso + "ehs_output.txt")

    if not os.path.exists(log):
        open(log, 'a').close()
    f = open(log, 'a')
    f.write(arcpy.GetMessages())
    f.close()

def clean_scratch(scratch_workspace):
    for the_file in os.listdir(scratch_workspace):
        file_path = os.path.join(scratch_workspace, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)
