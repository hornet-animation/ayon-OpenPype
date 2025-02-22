from openpype.pipeline import install_host
from openpype.hosts.nuke.api import NukeHost
from hornet_deadline_utils import deadlineNetworkSubmit
host = NukeHost()
install_host(host)

# TODO horent:old heck with output format, see hornet commit 153ccd9
import nuke
import os
import json

from openpype.lib import Logger
from openpype.hosts.nuke import api
from openpype.hosts.nuke.api.lib import (
    on_script_load,
    check_inventory_versions,
    WorkfileSettings,
    dirmap_file_name_filter,
    add_scripts_gizmo,
    create_write_node
)
from openpype.settings import get_project_settings

log = Logger.get_logger(__name__)
# dict mapping extension to list of exposed parameters from write node to top level group node
knobMatrix = { 'exr': ['autocrop', 'datatype', 'heroview', 'metadata', 'interleave'],
                'png': ['datatype'],
                'dpx': ['datatype'],
                'tiff': ['datatype', 'compression'],
                'jpeg': []
}
universalKnobs = ['colorspace', 'views']

knobMatrix = {key: universalKnobs + value for key, value in knobMatrix.items()}
presets = {
    'exr' : [ ("colorspace", 'scene_linear'), ('channels', 'all'), ('datatype', '16 bit half') ],
    'png' : [ ("colorspace", 'color_picking'), ('channels', 'rgba'), ('datatype','16 bit') ],
    'dpx' : [ ("colorspace", 'color_picking'), ('channels', 'rgb'), ('datatype','10 bit'), ('big endian', True) ],
    'jpeg' : [ ("colorspace", 'matte_paint'), ('channels', 'rgb') ]
           }
def apply_format_presets():
    node = nuke.thisNode()
    knob = nuke.thisKnob()
    if knob.name() == 'file_type':
        if knob.value() in presets.keys():
            for preset in presets[knob.value()]:
                if node.knob(preset[0]):
                    node.knob(preset[0]).setValue(preset[1])
# Hornet- helper to switch file extension to filetype
def writes_ver_sync():
    ''' Callback synchronizing version of publishable write nodes
    '''
    try:
        print('Hornet- syncing version to write nodes')
        #rootVersion = pype.get_version_from_path(nuke.root().name())
        pattern = re.compile(r"[\._]v([0-9]+)", re.IGNORECASE)
        rootVersion = pattern.findall(nuke.root().name())[0]
        padding = len(rootVersion)
        new_version = "v" + str("{" + ":0>{}".format(padding) + "}").format(
            int(rootVersion)
        )
        print("new_version: {}".format(new_version))
    except Exception as e:
        print(e)
        return
    groupnodes = [node.nodes() for node in nuke.allNodes() if node.Class() == 'Group']
    allnodes = [node for group in groupnodes for node in group] + nuke.allNodes()
    for each in allnodes:
        if each.Class() == 'Write':
            # check if the node is avalon tracked
            if each.name().startswith('inside_'):
                avalonNode = nuke.toNode(each.name().replace('inside_',''))
            else:
                avalonNode = each
            if "AvalonTab" not in avalonNode.knobs():
                print("tab failure")
                continue

            avalon_knob_data = avalon.nuke.get_avalon_knob_data(
                avalonNode, ['avalon:', 'ak:'])
            try:
                if avalon_knob_data['families'] not in ["render", "write"]:
                    print("families fail")
                    log.debug(avalon_knob_data['families'])
                    continue

                node_file = each['file'].value()

                #node_version = "v" + pype.get_version_from_path(node_file)
                node_version = 'v' + pattern.findall(node_file)[0]

                log.debug("node_version: {}".format(node_version))

                node_new_file = node_file.replace(node_version, new_version)
                each['file'].setValue(node_new_file)
                #H: don't need empty folders if work file isn't rendered later
                #if not os.path.isdir(os.path.dirname(node_new_file)):
                #    log.warning("Path does not exist! I am creating it.")
                #    os.makedirs(os.path.dirname(node_new_file), 0o766)
            except Exception as e:
                print(e)
                log.warning(
                    "Write node: `{}` has no version in path: {}".format(
                        each.name(), e))


def switchExtension():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    if knb == nde.knob('file_type'):
        filek = nde.knob('file')
        old = filek.value()
        pre,ext = os.path.splitext(old)
        filek.setValue(pre + '.' + knb.value())

def embedOptions():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    log.info(' knob of type' + str(knb.Class()))
    htab = nuke.Tab_Knob('htab','Hornet')
    htab.setName('htab')
    if knb == nde.knob('file_type'):
        group = nuke.toNode('.'.join(['root'] + nde.fullName().split('.')[:-1]))
        ftype = knb.value()
    else:
        return
    if ftype not in knobMatrix.keys():
        return
    for knb in group.allKnobs():
        try:
            #never clear or touch the invisible string knob that contains the pipeline JSON data
            if knb.name() != api.INSTANCE_DATA_KNOB:
                group.removeKnob(knb)
        except:
            continue
    beginGroup = nuke.Tab_Knob('beginoutput', 'Output', nuke.TABBEGINGROUP)
    group.addKnob(beginGroup)

    if 'file' not in group.knobs().keys():
        fle = nuke.Multiline_Eval_String_Knob('File output')
        fle.setText(nde.knob('file').value())
        group.addKnob(fle)
        link = nuke.Link_Knob('channels')
        link.makeLink(nde.name(), 'channels')
        link.setName('channels')
        group.addKnob(link)
        if 'file_type' not in group.knobs().keys():
            link = nuke.Link_Knob('file_type')
            link.makeLink(nde.name(), 'file_type')
            link.setName('file_type')
            link.setFlag(0x1000)
            group.addKnob(link)
        for kname in knobMatrix[ftype]:
            link = nuke.Link_Knob(kname)
            link.makeLink(nde.name(), kname)
            link.setName(kname)
            link.setFlag(0x1000)
            group.addKnob(link)
    log.info("links made")
    renderFirst = nuke.Link_Knob('first')
    renderFirst.makeLink(nde.name(), 'first')
    renderFirst.setName('Render Start')

    renderLast = nuke.Link_Knob('last')
    renderLast.makeLink(nde.name(), 'last')
    renderLast.setName('Render End')

    publishFirst = nuke.Int_Knob('publishFirst', 'Publish Start')
    publishLast = nuke.Int_Knob('publishLast', 'Publish End')
    usePublishRange = nuke.Boolean_Knob('usePublishRange', 'My Publish Range is different from my render range')
    usePublishRange.setFlag(nuke.STARTLINE)
    nde.knob('first').setValue(nuke.root().firstFrame())
    nde.knob('last').setValue(nuke.root().lastFrame())
    publishFirst.setValue(nuke.root().firstFrame())
    publishLast.setValue(nuke.root().lastFrame())
    publishFirst.setEnabled(False)
    publishLast.setEnabled(False)
    usePublishRange.setValue(False)

    endGroup = nuke.Tab_Knob('endoutput', None, nuke.TABENDGROUP)
    group.addKnob(endGroup)
    beginGroup = nuke.Tab_Knob('beginpipeline', 'Rendering and Pipeline', nuke.TABBEGINGROUP)
    group.addKnob(beginGroup)

    publishFirst.clearFlag(nuke.STARTLINE)
    group.addKnob(renderFirst)

    group.addKnob(publishFirst)
    publishLast.clearFlag(nuke.STARTLINE)
    group.addKnob(renderLast)
    group.addKnob(publishLast)
    group.addKnob(usePublishRange)

    sub = nuke.PyScript_Knob('submit', 'Submit to Deadline', "deadlineNetworkSubmit()")
    sub.setFlag(nuke.STARTLINE)
    clr = nuke.PyScript_Knob('clear', 'Clear Temp Outputs', "import os;fpath = os.path.dirname(nuke.thisNode().knob('File output').value());[os.remove(os.path.join(fpath, f)) for f in os.listdir(fpath)]")
    pub = nuke.PyScript_Knob('publish', 'Publish', "from openpype.tools.utils import host_tools;host_tools.show_publisher(tab='Publish')")
    readfrom_src = "import write_to_read;write_to_read.write_to_read(nuke.thisNode(), allow_relative=False)"
    readfrom = nuke.PyScript_Knob('readfrom', 'Read From Rendered', readfrom_src)
    link = nuke.Link_Knob('render')
    link.makeLink(nde.name(), 'Render')
    link.setName('Render Local')
    link.setFlag(nuke.STARTLINE)
    group.addKnob(link)

    div = nuke.Text_Knob('div','','')
    deadlinediv = nuke.Text_Knob('deadlinediv','Deadline','')
    deadlinePriority = nuke.Int_Knob('deadlinePriority', 'Priority')
    deadlinePool = nuke.String_Knob('deadlinePool', 'Pool')
    deadlineGroup = nuke.String_Knob('deadlineGroup', 'Group')
    deadlineChunkSize = nuke.Int_Knob('deadlineChunkSize', 'Chunk Size')
    deadlineChunkSize.setValue(1)
    deadlinePool.setValue('local')
    deadlineGroup.setValue('nuke')
    deadlinePriority.setValue(90)
    deadlineChunkSize.clearFlag(nuke.STARTLINE)
    group.addKnob(readfrom)
    group.addKnob(clr)
    group.addKnob(deadlinediv)
    group.addKnob(deadlinePriority)
    group.addKnob(deadlineChunkSize)
    group.addKnob(deadlinePool)
    group.addKnob(deadlineGroup)
    group.addKnob(sub)
    group.addKnob(div)
    group.addKnob(pub)
    tempwarn = nuke.Text_Knob('tempwarn', '', '- all rendered files are TEMPORARY and WILL BE OVERWRITTEN unless published ')
    group.addKnob(tempwarn)

    endGroup = nuke.Tab_Knob('endpipeline', None, nuke.TABENDGROUP)
    group.addKnob(endGroup)

def quick_write_node(family='render'):
    if any(var is None or var == '' for var in [os.environ['AVALON_TASK'],os.environ['AVALON_ASSET']]):
        nuke.alert("missing AVALON_TASK and AVALON_ASSET, can't make quick write")

    variant = nuke.getInput('Variant for Quick Write Node','Main').title()
    variant = '_' + variant if variant[0] != '_' else variant
    if variant == '_' or variant == None or variant == '':
        nuke.message('No Variant Specified, will not create Write Node')
        return
    for nde in nuke.allNodes('Write'):
        if nde.knob('name').value() == family + os.environ['AVALON_TASK'] + variant:
            nuke.message('Write Node already exists')
            return
    data = {'subset':family + os.environ['AVALON_TASK'] + variant,'variant': variant,
            'id':'pyblish.avalon.instance','creator': f'create_write_{family}','creator_identifier': f'create_write_{family}',
            'folderPath': os.environ['AVALON_ASSET'], 'task': os.environ['AVALON_TASK'], 
            'family': family,
            'fpath_template':"{work}/renders/nuke/{subset}/{subset}.{frame}.{ext}"}
    qnode = create_write_node(family + os.environ['AVALON_TASK'] + variant,
                              data,
                              prerender=True if family == 'prerender' else False)
    qnode = nuke.toNode(family + os.environ['AVALON_TASK'] + variant)
    print(f'Created Write Node: {qnode.name()}')
    api.set_node_data(qnode,api.INSTANCE_DATA_KNOB,data)
    instance_data = json.loads(qnode.knob(api.INSTANCE_DATA_KNOB).value()[7:])
    instance_data['task'] = os.environ['AVALON_TASK']
    instance_data['creator_attributes'] = {'render_taget': 'frames_farm', 'review': True}
    instance_data['publish_attributes'] = {"CollectFramesFixDef": {"frames_to_fix": "", "rewrite_version": False},
                                                                 "ValidateCorrectAssetContext": {"active": True},
                                                                 "NukeSubmitDeadline": {"priority": 90, "chunk": 1, "concurrency": 1, "use_gpu": True, "suspend_publish": False, "workfile_dependency": True, "use_published_workfile": True}}
    print(instance_data)
    qnode.knob(api.INSTANCE_DATA_KNOB).setValue("JSON:::" + json.dumps(instance_data))
    with qnode.begin():
        inside_write = nuke.toNode('inside_'+ family + os.environ['AVALON_TASK'] + variant.title())
        inside_write.knob('file_type').setValue('exr')
def enable_disable_frame_range():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    if not nde.knob('use_limit') or not knb.name() == 'use_limit':
        return
    group = nuke.toNode('.'.join(['root'] + nde.fullName().split('.')[:-1]))
    enable = nde.knob('use_limit').value()
    group.knobs()['first'].setEnabled(enable)
    group.knobs()['last'].setEnabled(enable)

def submit_selected_write():
    for nde in nuke.selectedNodes():
        if nde.Class() == 'Write':
            submit_write(nde)
def enable_publish_range():
    nde = nuke.thisNode()
    kb = nuke.thisKnob()
    if not kb == nde.knob('usePublishRange'):
        return
    if kb.value():
        nde.knob('publishFirst').setEnabled(True)
        nde.knob('publishLast').setEnabled(True)
    else:
        nde.knob('publishFirst').setEnabled(False)
        nde.knob('publishLast').setEnabled(False)

hornet_menu = nuke.menu("Nuke")
m = hornet_menu.addMenu("&Hornet")
m.addCommand("&Quick Write Node", "quick_write_node()", "Ctrl+W")
m.addCommand("&Quick PreWrite Node", "quick_write_node(family='prerender')", "Ctrl+Shift+W")
nuke.addKnobChanged(apply_format_presets, nodeClass='Write')
nuke.addKnobChanged(switchExtension, nodeClass='Write')
nuke.addKnobChanged(embedOptions, nodeClass='Write')
nuke.addKnobChanged(enable_publish_range, nodeClass='Group')
nuke.addKnobChanged(enable_disable_frame_range, nodeClass='Write')
nuke.addOnScriptSave(writes_ver_sync)
