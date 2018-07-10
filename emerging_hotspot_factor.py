import os
import arcpy
import datetime
import utilities


def emerging_hs_points(tile_grid, lossyearmosaic, hansenareamosaic, country_shapefile,
                       country_shapefile_int, datadir, iso, remap_table, year_remap_function, snap_results, tcd_masks):

    # create directories
    scratch_workspace = utilities.scratch_folder(datadir)
    results_gdb = utilities.results_gdb(datadir, "results")
    scratch_gdb_workspace = utilities.results_gdb(datadir, "scratch")

    # set environments
    arcpy.env.scratchWorkspace = scratch_workspace
    arcpy.env.workspace = datadir
    arcpy.env.snapRaster = hansenareamosaic
    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = "TRUE"
    start = datetime.datetime.now()

    # create tcd country masks
    print(" creating list of 30% tcd mask that intersect country boundary")
    tile_list = utilities.select_tiles(country_shapefile, tile_grid)

    print(" clipping 30% tcd mask to country boundary")
    clipped_mask_list = utilities.clipped_mask_list(tile_list, country_shapefile, scratch_workspace, tcd_masks)


    print(" merging masks")
    merged_country_mask = utilities.merge_clipped_masks(clipped_mask_list, results_gdb, iso)

    print(" simplifying mask")
    simplified_mask = utilities.merge_polygon_simplify(merged_country_mask, results_gdb, iso)

    print("     extracting loss data with tcd mask")
    extract_file = utilities.extract_loss(scratch_workspace, lossyearmosaic, country_shapefile_int, iso,
                                          scratch_gdb_workspace)


    # loop over years 2001-2017
    for short_year in range(1, 18):

        print("\nPROCESSING RASTER VALUE {} (YEAR = {})".format(short_year, 2000 + short_year))
        # reclassify per year
        utilities.update_remap_table(remap_table, short_year)

        # update reclass function using table
        utilities.update_reclass_function(extract_file, year_remap_function)

        print("     aggregating remapped loss data by 80")
        loss_aggregate = utilities.aggregate(scratch_workspace, iso, extract_file, snap_results)

        print("     converting loss data to point")
        temp_points = utilities.raster_to_point(results_gdb, iso, loss_aggregate, short_year)

        # add date for individual year
        if temp_points:
            print("     adding date to point file")
            utilities.add_date(temp_points, short_year)

            # create point feature class or append to existing
            all_points = utilities.create_append_fc(results_gdb, iso, temp_points, short_year)

    print("     create space time cube")

    cube = utilities.create_space_time_cube(all_points, datadir, iso)

    try:
        print("       create hot spots")
        utilities.create_hot_spots(cube, results_gdb, iso, simplified_mask, datadir)

    except:
        print("        failed")

    print("       empty scratch folder")
    arcpy.Delete_management(scratch_workspace)

    # print time for each AOI
    end = datetime.datetime.now() - start
    arcpy.AddMessage(iso + " EHS took this long: " + str(end))
