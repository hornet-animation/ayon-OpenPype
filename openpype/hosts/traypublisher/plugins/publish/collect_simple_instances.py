import os
import tempfile

import clique
import pyblish.api


class CollectSettingsSimpleInstances(pyblish.api.InstancePlugin):
    """Collect data for instances created by settings creators.

    Plugin create representations based on 'filepath' attribute stored
    on instance.

    Representations can be marked for review and in that case is also added
    'review' family to instance families. For review can be marked only one
    representation so **first** representation that has extension available
    in '_review_extensions' is used for review.

    For 'source' on instance is used path from last created representation.

    Set staging directory on instance. That is probably never used because
    each created representation has it's own staging dir.
    """

    label = "Collect Settings Simple Instances"
    order = pyblish.api.CollectorOrder - 0.49

    hosts = ["traypublisher"]

    def process(self, instance):
        if not instance.data.get("settings_creator"):
            return

        instance_label = instance.data["name"]
        # Create instance's staging dir in temp
        tmp_folder = tempfile.mkdtemp(prefix="traypublisher_")
        instance.data["stagingDir"] = tmp_folder
        instance.context.data["cleanupFullPaths"].append(tmp_folder)

        self.log.debug((
            "Created temp staging directory for instance {}. {}"
        ).format(instance_label, tmp_folder))

        # Store filepaths for validation of their existence
        source_filepaths = []
        # Make sure there are no representations with same name
        repre_names_counter = {}
        # Store created names for logging
        repre_names = []
        # Store set of filepaths per each representation
        representation_files_mapping = []
        source = self._create_main_representations(
            instance,
            source_filepaths,
            repre_names_counter,
            repre_names,
            representation_files_mapping
        )

        self._create_review_representation(
            instance,
            source_filepaths,
            repre_names_counter,
            repre_names,
            representation_files_mapping
        )

        instance.data["source"] = source
        instance.data["sourceFilepaths"] = list(set(source_filepaths))

        self.log.debug(
            (
                "Created Simple Settings instance \"{}\""
                " with {} representations: {}"
            ).format(
                instance_label,
                len(instance.data["representations"]),
                ", ".join(repre_names)
            )
        )

    def _create_main_representations(
        self,
        instance,
        source_filepaths,
        repre_names_counter,
        repre_names,
        representation_files_mapping
    ):
        creator_attributes = instance.data["creator_attributes"]
        filepath_items = creator_attributes["representation_files"]
        if not isinstance(filepath_items, list):
            filepath_items = [filepath_items]

        source = None
        for filepath_item in filepath_items:
            # Skip if filepath item does not have filenames
            if not filepath_item["filenames"]:
                continue

            filepaths = {
                os.path.join(filepath_item["directory"], filename)
                for filename in filepath_item["filenames"]
            }
            source_filepaths.extend(filepaths)

            source = self._calculate_source(filepaths)
            representation = self._create_representation_data(
                filepath_item, repre_names_counter, repre_names
            )
            instance.data["representations"].append(representation)
            representation_files_mapping.append(
                (filepaths, representation, source)
            )
        return source

    def _create_review_representation(
        self,
        instance,
        source_filepaths,
        repre_names_counter,
        repre_names,
        representation_files_mapping
    ):
        # Skip review representation creation if there are no representations
        #   created for "main" part
        #   - review representation must not be created in that case so
        #       validation can care about it
        if not representation_files_mapping:
            self.log.warning((
                "There are missing source representations."
                " Creation of review representation was skipped."
            ))
            return

        creator_attributes = instance.data["creator_attributes"]
        review_file_item = creator_attributes["reviewable"]
        filenames = review_file_item.get("filenames")
        if not filenames:
            self.log.debug((
                "Filepath for review is not defined."
                " Skipping review representation creation."
            ))
            return

        filepaths = {
            os.path.join(review_file_item["directory"], filename)
            for filename in filenames
        }
        source_filepaths.extend(filepaths)
        # First try to find out representation with same filepaths
        #   so it's not needed to create new representation just for review
        review_representation = None
        # Review path (only for logging)
        review_path = None
        for item in representation_files_mapping:
            _filepaths, representation, repre_path = item
            if _filepaths == filepaths:
                review_representation = representation
                review_path = repre_path
                break

        if review_representation is None:
            self.log.debug("Creating new review representation")
            review_path = self._calculate_source(filepaths)
            review_representation = self._create_representation_data(
                review_file_item, repre_names_counter, repre_names
            )
            instance.data["representations"].append(review_representation)

        if "review" not in instance.data["families"]:
            instance.data["families"].append("review")

        review_representation["tags"].append("review")
        self.log.debug("Representation {} was marked for review. {}".format(
            review_representation["name"], review_path
        ))

    def _create_representation_data(
        self, filepath_item, repre_names_counter, repre_names
    ):
        """Create new representation data based on file item.

        Args:
            filepath_item (Dict[str, Any]): Item with information about
                representation paths.
            repre_names_counter (Dict[str, int]): Store count of representation
                names.
            repre_names (List[str]): All used representation names. For
                logging purposes.

        Returns:
            Dict: Prepared base representation data.
        """

        filenames = filepath_item["filenames"]
        _, ext = os.path.splitext(filenames[0])
        if len(filenames) == 1:
            filenames = filenames[0]

        repre_name = repre_ext = ext[1:]
        if repre_name not in repre_names_counter:
            repre_names_counter[repre_name] = 2
        else:
            counter = repre_names_counter[repre_name]
            repre_names_counter[repre_name] += 1
            repre_name = "{}_{}".format(repre_name, counter)
        repre_names.append(repre_names)
        return {
            "ext": repre_ext,
            "name": repre_name,
            "stagingDir": filepath_item["directory"],
            "files": filenames,
            "tags": []
        }

    def _calculate_source(self, filepaths):
        cols, rems = clique.assemble(filepaths)
        if cols:
            source = cols[0].format("{head}{padding}{tail}")
        elif rems:
            source = rems[0]
        return source
