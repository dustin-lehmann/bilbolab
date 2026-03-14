import json


def main():
    out = {
        'obstacle': {
            'BabylonObject': 'PysimBox',
            'config': {
                'color': [0.5, 0.5, 0.5],
                'texture': '',
                'wireframe': False
            }
        },
        'floor_tile': {
            'BabylonObject': 'PysimBox',
            'config': {
                'color': [0.7, 0.7, 0.7],
                'texture': '/textures/material/floor_bright.png',
                 'texture_uscale': 1,
                 'texture_vscale': 1,
            }
        },
        'grid_cell_2d': {
            'BabylonObject': 'GridCell2D',
            'config': {
                'color': [0.7, 0.7, 0.7],
                'texture': '/textures/material/floor_bright.png',
                'texture_uscale': 1,
                'texture_vscale': 1,
            }
        },
        'tank_robot': {
            'BabylonObject': 'PysimBox',
            'config': {
                'color': [0, 1, 0],
            }
        },
        'twipr_agent_old': {
            'BabylonObject': 'PysimBox',
            'config': {
                'color': [0, 0, 1],
            },
        },
        'twipr_agent': {
            'BabylonObject': 'TWIPR_Robot',
            'config': {
                'base_model': './models/BILBO/twipr_',
                'show_collision_frame': False,
            },
        },
        'twipr_agent_double_pendulum': {
            'BabylonObject': 'TWIPR_Robot_DoublePendulum',
            'config': {
                'base_model': './models/BILBO/twipr_',
                'show_collision_frame': False,
            },
        },
            'diff_drive_robot': {
                'BabylonObject': 'DiffDriveRobot',
                'config': {
                    'base_model': './models/diff_drive_robot/diff_robot_',
                    'show_collision_frame': False,
                },
        }
    }

    with open("object_config.json", "w") as output_file:
        json.dump(out, output_file, indent=2)


if __name__ == '__main__':
    main()
