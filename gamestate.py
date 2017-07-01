import itertools
import math
import random
from operator import xor

import numpy as np
import pygame
import zope.event

import ball
import config
import cue
import event
import graphics
import table_sprites


class BallType(Enum):
    Striped = "stripes"
    Solid = "solid"


class Player(Enum):
    Player1 = 1
    Player2 = 2


class GameState:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(config.window_caption)
        zope.event.subscribers.append(self.game_event_handler)
        self.canvas = graphics.Canvas()
        self.fps_clock = pygame.time.Clock()

    def fps(self):
        return self.fps_clock.get_fps()

    def mark_one_frame(self):
        self.fps_clock.tick(config.fps_limit)

    def create_white_ball(self):
        self.white_ball = ball.BallSprite(0)
        self.white_ball.move_to(config.white_ball_initial_pos)
        self.balls.add(self.white_ball)
        self.all_sprites.add(self.white_ball)

    def game_event_handler(self, event):
        if event.type == "POTTED":
            self.table_coloring.update(self)
            self.potted.append(event.data.number)
        elif event.type == "COLLISION":
            if not self.white_ball_1st_hit_is_set:
                self.first_collision(event.data)

    def set_pool_balls(self):
        counter = [0, 0]
        coord_shift = np.array([math.sin(math.radians(60)) * config.ball_radius *
                                2, -config.ball_radius])
        initial_place = config.ball_starting_place_ratio * config.resolution

        self.create_white_ball()
        # randomizes the sequence of balls on the table
        ball_placement_sequence = list(range(1, config.total_ball_num))
        random.shuffle(ball_placement_sequence)

        for i in ball_placement_sequence:
            ball_iteration = ball.BallSprite(i)
            ball_iteration.move_to(initial_place + coord_shift * counter)
            if counter[1] == counter[0]:
                counter[0] += 1
                counter[1] = -counter[0]
            else:
                counter[1] += 2
            self.balls.add(ball_iteration)

        self.all_sprites.add(self.balls)

    def start_pool(self):
        self.create_variables()
        self.generate_table()
        self.set_pool_balls()
        self.cue = cue.Cue(self.white_ball)
        self.all_sprites.add(self.cue)

    def create_variables(self):
        # game state variables
        self.current_player = Player.Player1
        self.turn_ended = True
        self.white_ball_1st_hit_is_set = False
        self.white_ball_1st_hit_is_stripes = False
        self.potted = []
        self.balls = pygame.sprite.Group()
        self.holes = pygame.sprite.Group()
        self.all_sprites = pygame.sprite.OrderedUpdates()
        self.turn_number = 0
        self.stripes_decided = False
        self.player1_stripes = False
        self.can_move_white_ball = True
        self.stripes_remaining = True
        self.solids_remaining = True
        self.player1_pots_8ball = False
        self.player2_pots_8ball = False
        self.table_sides = []

    def is_behind_line_break(self):
        # 1st break should be made from behind the separation line on the table
        return self.turn_number == 0

    def redraw_all(self, update=True):
        self.all_sprites.clear(self.canvas.surface, self.canvas.background)
        self.all_sprites.draw(self.canvas.surface)
        self.all_sprites.update(self)
        if update:
            pygame.display.flip()
        self.mark_one_frame()

    def all_not_moving(self):
        return_value = True
        for ball in self.balls:
            if np.count_nonzero(ball.velocity) > 0:
                return_value = False
                break
        return return_value

    def generate_table(self):
        table_side_points = np.empty((1, 2))
        # holes_x and holes_y holds the possible xs and ys table holes
        # with a position ID in the second tuple field
        # so the top left hole has id 1,1
        holes_x = [(config.table_margin, 1), (config.resolution[0] /
                                              2, 2), (config.resolution[0] - config.table_margin, 3)]
        holes_y = [(config.table_margin, 1),
                   (config.resolution[1] - config.table_margin, 2)]
        # next three lines are a hack to make and arrange the hole coordinates
        # in the correct sequence
        all_hole_positions = np.array(
            list(itertools.product(holes_y, holes_x)))
        all_hole_positions = np.fliplr(all_hole_positions)
        all_hole_positions = np.vstack(
            (all_hole_positions[:3], np.flipud(all_hole_positions[3:])))
        for hole_pos in all_hole_positions:
            self.holes.add(table_sprites.Hole(hole_pos[0][0], hole_pos[1][0]))
            # this will generate the diagonal, vertical and horizontal table
            # pieces which will reflect the ball when it hits the table sides
            # they are generated using 4x2 offset matrices (4 points around the hole)
            # with the first point of the matrix is the starting point and the
            # last point is the ending point, these 4x2 matrices are
            # concatenated together
            # also the martices must be flipped using numpy.flipud()
            # after reflecting them using 2x1 reflection matrices, otherwise
            # starting and ending points would be reversed
            if hole_pos[0][1] == 2:
                # hole_pos[0,1]=2 means x coordinate ID is 2 which means this
                # hole is in the middle
                offset = config.middle_hole_offset
            else:
                offset = config.side_hole_offset
            if hole_pos[1][1] == 2:
                offset = np.flipud(offset) * [1, -1]
            if hole_pos[0][1] == 1:
                offset = np.flipud(offset) * [-1, 1]
            table_side_points = np.append(
                table_side_points, [hole_pos[0][0], hole_pos[1][0]] + offset, axis=0)
        # deletes the 1st point in array (leftover form np.empty)
        table_side_points = np.delete(table_side_points, 0, 0)
        for num, point in enumerate(table_side_points[:-1]):
            # this will skip lines inside the circle
            if num % 4 != 1:
                self.table_sides.append(table_sprites.TableSide(
                    [point, table_side_points[num + 1]]))
        self.table_sides.append(table_sprites.TableSide(
            [table_side_points[-1], table_side_points[0]]))
        self.table_coloring = table_sprites.TableColoring(
            config.resolution, config.table_side_color, table_side_points)
        self.all_sprites.add(self.table_coloring)
        self.all_sprites.add(self.holes)
        graphics.add_separation_line(self.canvas)

    def game_over(self, p1_won):
        # when the game is over a message is displayed
        font = config.get_default_font(config.game_over_label_font_size)
        if p1_won:
            text = "PLAYER 1 WON!"
        else:
            text = "PLAYER 2 WON!"
        rendered_text = font.render(text, False, (255, 255, 255))
        self.canvas.surface.blit(rendered_text, (config.resolution - font.size(text)) / 2)
        pygame.display.flip()
        while not (event.events()["closed"] or event.events()["clicked"]):
            pass

    def turn_over(self, penalize):
        if not self.turn_ended:
            self.turn_ended = True
            self.turn_number += 1
            if self.current_player.value == 1:
                self.current_player = Player.Player2
            else:
                self.current_player = Player.Player1
        if penalize:
            self.can_move_white_ball = True

    def check_potted(self):
        self.can_move_white_ball = False
        # if white ball is potted, it will be created again and placed in the middle
        if 0 in self.potted:
            self.create_white_ball()
            self.cue.target_ball = self.white_ball
            self.potted.remove(0)
            self.turn_over(True)
        if 8 in self.potted:
            if self.p1_p2_condition(self.player1_pots_8ball, self.player2_pots_8ball):
                self.game_over(self.current_player.value == 1)
            else:
                self.game_over(self.current_player.value == 2)
            self.potted.remove(8)

    def check_remaining(self):
        # a check if all striped or solid balls were potted
        stripes_remaining = False
        solids_remaining = False
        for remaining_ball in self.balls:
            if remaining_ball.get_number() != 0 and remaining_ball.get_number() != 8:
                stripes_remaining = stripes_remaining or remaining_ball.is_striped
                solids_remaining = solids_remaining or not remaining_ball.is_striped
        self.stripes_remaining = stripes_remaining
        self.solids_remaining = solids_remaining

        # decides if on of the players (or both) should be potting 8ball
        self.player1_pots_8ball = self.p1_striped_condition(not stripes_remaining, not solids_remaining)
        self.player2_pots_8ball = self.p1_striped_condition(not solids_remaining, not stripes_remaining)

    def first_collision(self, ball_combination):
        self.white_ball_1st_hit_is_set = True
        self.white_ball_1st_hit_8ball = ball_combination[0].get_number() == 8 or ball_combination[1].get_number() == 8
        if ball_combination[0].get_number() == 0:
            self.white_ball_1st_hit_is_stripes = ball_combination[1].is_striped
        else:
            self.white_ball_1st_hit_is_stripes = ball_combination[0].is_striped

    def check_pool_rules(self):
        self.check_remaining()
        self.check_potted()
        self.first_hit_rule()
        self.potted_ball_rules()
        self.on_next_hit()

    def on_next_hit(self):
        self.white_ball_1st_hit_is_set = False
        self.turn_ended = False
        self.potted = []

    def p1_p2_condition(self, p1_condition, p2_condition):
        # returns a variable depending on which players move it is right now
        if self.current_player.value == 1:
            return p1_condition
        else:
            return p2_condition

    def p1_striped_condition(self, striped_condition, solids_condition):
        # returns striped condition if p1 is potting stripes
        if self.ball_assignment is not None:
            if self.ball_assignment[Player.Player1] == BallType.Striped:
                return striped_condition
            else:
                return solids_condition


    def potted_ball_rules(self):
        if len(self.potted) > 0:
            # if it wasnt decided which player goes for which type of balls
            # and the player potted the balls exclusively of one color (excluting white balls)
            # then it is decided based on which players turn it is right now and which type
            # of balls he potted
            potted_stripe_count = len([x for x in self.potted if x > 8])
            potted_solid_count = len([x for x in self.potted if x < 8])
            only_stripes_potted = potted_solid_count == 0 and potted_stripe_count > 0
            only_solids_potted = potted_stripe_count == 0 and potted_solid_count > 0

            if only_solids_potted or only_stripes_potted:
                selected_ball_type = BallType.Striped if only_stripes_potted else BallType.Solid
                if self.ball_assignment is None:
                    # TODO: Add current player to the class
                    # unpacking a singular set - SO MACH HACK
                    other_player, = set(Player) - {self.current_player}
                    other_ball_type, = set(BallType) - {selected_ball_type}
                    self.ball_assignment = {self.current_player: selected_ball_type, other_player: other_ball_type}
                elif self.ball_assignment is not None and self.ball_assignment[self.current_player] != selected_ball_type:
                    self.turn_over(False)
        else:
            self.turn_over(False)

    def first_hit_rule(self):
        # checks if the 1st white ball hit is the same as the players target ball type
        # for example if the first white hit of the white ball is a striped ball,
        # but the player hits a solid ball, it is next players turn and he can move the white ball
        if not self.white_ball_1st_hit_is_set:
            self.turn_over(True)
        else:
            if self.stripes_decided and not self.white_ball_1st_hit_8ball:
                if self.p1_p2_condition(
                        not self.p1_striped_condition(self.white_ball_1st_hit_is_stripes,
                                                      not self.white_ball_1st_hit_is_stripes),
                        not self.p1_striped_condition(not self.white_ball_1st_hit_is_stripes,
                                                      self.white_ball_1st_hit_is_stripes)):
                    self.turn_over(True)

            # checks if the 8ball was the first ball hit, and if so checks if the player needs to pot the 8ball
            # and if not he gets penalised
            if self.white_ball_1st_hit_8ball and \
                    not self.p1_p2_condition(self.player1_pots_8ball, self.player2_pots_8ball):
                self.turn_over(True)

