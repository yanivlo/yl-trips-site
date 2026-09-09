#!/bin/csh

#cp ~/Projects/location-history/outputs/oregon_trip_map.html ~/Projects/yl-trips-site/oregon/index.html
#cp ~/Projects/location-history/outputs/adirondacks_trip_map.html ~/Projects/yl-trips-site/adirondacks/index.html

# yes | cp -rf ~/Projects/location-history/application/scratch/adirondacks/ ~/Projects/yl-trips-site/


git status

echo -n "Proceed with git add --all? (y/n): "
set confirm = "$<"

if ( "$confirm" != "y" ) then
    echo "Aborted."
    exit 1
endif

git add --all

echo -n "Enter commit description: "
set desc = "$<"

git commit -m "$desc"

echo -n "Proceed with git push? (y/n): "
set confirm_push = "$<"

if ( "$confirm_push" == "y" ) then
    git push
else
    echo "Push aborted."
endif
