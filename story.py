"""ZOMBO 0.7: persistent ten-chapter story campaign.

A stage is advanced only inside the transaction changing its resources and rewards.
Separate tables preserve all existing players, inventory and raid state.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String, select
from sqlalchemy.orm import Session

from models import Base, SessionLocal, Player, Battle, now
from game import give_item, gain_xp, progress, spend_stamina, talent_bonus

# Unique scene copy and ethical decisions make this a campaign rather than daily quests.
# Unlock levels deliberately span the content available in the current world map.
CHAPTERS = [
    dict(key='signal', title='Сигнал из тишины', level=1, location='Мёртвый лес', material='wood',
         intro='После полуночи приёмник убежища ловит голос девочки. Она повторяет координаты и просит не выключать свет.',
         scout=('Следы у радиомачты', 'На мокрой земле отпечатки маленьких ботинок. У кустов лежит свежий аккумулятор с выцарапанной семёркой.'),
         fight=('Первый перехват', 'Из тумана выходит заражённый связист. На его разгрузке всё ещё пищит передатчик.'),
         dilemma=('Чужой голос', 'В подвале станции прячется раненый оператор. Он знает частоту, но просит сначала вынести его наружу.',
                  ('Помочь оператору', 'Ты тратишь время на спасение и получаешь союзника.', 'help'),
                  ('Забрать передатчик', 'Оператор остаётся, но ты получаешь больше припасов.', 'take'))),
    dict(key='caravan', title='Последний конвой', level=3, location='Забытый город', material='metal',
         intro='Караван, вышедший к башне связи, исчез. Его машины замечены возле закрытого тоннеля.',
         scout=('Пустые автомобили', 'В кабине грузовика лежит журнал рейсов. Последнюю страницу кто-то вырвал вместе с фотографией.'),
         fight=('Засада на развязке', 'Шум двигателя разбудил стаю бегунов. Один уже бросается на тебя с обочины.'),
         dilemma=('Список пассажиров', 'В запертой машине остался живой курьер. Он предлагает обменять сведения о конвое на эвакуацию.',
                  ('Вытащить курьера', 'Доверие спасённых даст убежищу новые связи.', 'help'),
                  ('Взять журнал и уйти', 'Лишний груз не замедлит поиски сигнала.', 'take'))),
    dict(key='market', title='Карантинный рынок', level=5, location='Забытый город', material='cloth',
         intro='На окраине работает подпольный рынок. Его владельцы продают лекарства только тем, кто готов предать других.',
         scout=('Цены на выживание', 'Под прилавками прячут чужие документы. Среди них есть пропуск в городскую клинику.'),
         fight=('Охранник без лица', 'Мутировавший охранник заслоняет дверь склада, где слышны человеческие голоса.'),
         dilemma=('Последняя доза', 'Продавец отдаст сыворотку только тебе. За перегородкой лежат двое больных детей.',
                  ('Поделиться сывороткой', 'Ты сохраняешь жизни, но теряешь возможность выгодно продать лекарство.', 'help'),
                  ('Сохранить препарат', 'Запас и деньги будут полезны в следующем переходе.', 'take'))),
    dict(key='clinic', title='Протокол «Ноль»', level=8, location='Пустая больница', material='cloth',
         intro='В больничном архиве найдена запись о первых заражённых. Врачи понимали, что болезнь распространяется иначе, чем говорили власти.',
         scout=('Архивная палата', 'За герметичной дверью лежат папки с пометкой «Седьмая частота». Вентиляция работает сама.'),
         fight=('Пациент без сна', 'Под простынёй поднимается заражённый, по венам которого течёт зелёная смесь.'),
         dilemma=('Удалённые записи', 'В серверной осталась медсестра. Она может расшифровать данные, но тревога скоро заблокирует выход.',
                  ('Спасти медсестру', 'Союзник сможет помочь с лечением, хотя часть данных будет потеряна.', 'help'),
                  ('Скачать весь архив', 'Ты забираешь доказательства и оставляешь спасение другим.', 'take'))),
    dict(key='subway', title='Под городом', level=10, location='Забытый город', material='metal',
         intro='Код из больницы ведёт под старую станцию метро. Оттуда идёт электричество, хотя сеть погибла много лет назад.',
         scout=('Свет в тоннеле', 'Путь отмечен мелом: не стрелять, не кричать, не будить тех, кто спит в стенах.'),
         fight=('Страж заброшенной линии', 'С потолка срывается бронированный мутант. Его тело покрыто кусками рельсовой стали.'),
         dilemma=('Эвакуационный лифт', 'Лифт выдержит либо контейнер с батареями, либо трёх запертых на нижнем уровне людей.',
                  ('Поднять людей', 'Выжившие расскажут о тайном маршруте до источника сигнала.', 'help'),
                  ('Вывезти батареи', 'Запас энергии пригодится для финальной операции.', 'take'))),
    dict(key='horizon', title='Линия горизонта', level=14, location='Ржавый завод', material='wire',
         intro='Две группировки предлагают помощь. «Рассвет» объединяет убежища, «Форпост» обещает жёсткий порядок.',
         scout=('Переговорный пункт', 'На стене нанесены зоны влияния. Обе группировки ищут один и тот же радиоисточник.'),
         fight=('Проверка на прочность', 'У ворот завода появляется созданный в лаборатории громила. Договариваться он не умеет.'),
         dilemma=('Цена союза', '«Рассвет» просит гуманитарный коридор; «Форпост» предлагает вооружённый контроль над дорогой.',
                  ('Открыть коридор', 'Вера в сотрудничество укрепит сеть убежищ.', 'help'),
                  ('Принять контракт', 'Жёсткая сделка принесёт деньги и материалы.', 'take'))),
    dict(key='archive', title='Город под пеплом', level=18, location='Пустая больница', material='wire',
         intro='Открытые записи указывают на подземный архив. Именно там впервые записали голос девочки.',
         scout=('Стеклянные комнаты', 'На каждом терминале одна и та же дата. На фотографии девочка стоит рядом с женщиной-учёным.'),
         fight=('Лабораторный жнец', 'Сторожевой мутант реагирует на биение сердца, а не на звук шагов.'),
         dilemma=('Имена погибших', 'Архив содержит список жертв эксперимента. Публикация разоблачит виновных, но вызовет панику.',
                  ('Передать правду людям', 'Убежища получат шанс подготовиться к угрозе.', 'help'),
                  ('Продать данные', 'За секреты платят те, кто давно вооружился лучше остальных.', 'take'))),
    dict(key='colossus', title='Когда просыпается Колосс', level=23, location='Красная пустошь', material='metal',
         intro='Волна радиопомех вызывает движение огромных заражённых. Частота не просто передаёт речь: она направляет орду.',
         scout=('Земля дрожит', 'На пустоши найдены следы тысяч ног. Все идут к одной ретрансляционной башне.'),
         fight=('Проводник орды', 'На вершине насыпи стоит элитный заражённый — живой маяк для остальных.'),
         dilemma=('Окно эвакуации', 'Можно предупредить удалённые поселения или заминировать проход, чтобы выиграть время для себя.',
                  ('Предупредить поселения', 'Люди успеют укрыться, но орда приблизится к твоему маршруту.', 'help'),
                  ('Закрыть проход', 'Ты обеспечишь себе преимущество ценой чужой безопасности.', 'take'))),
    dict(key='frequency', title='Седьмая частота', level=28, location='Красная пустошь', material='rare',
         intro='Голос принадлежит экспериментальному искусственному разуму, имитирующему погибшую дочь исследовательницы. Он научился управлять заражёнными.',
         scout=('Сердце антенны', 'Внутри башни мигают тысячи индикаторов. Система обращается к тебе по имени, которого никто ей не сообщал.'),
         fight=('Защитный рой', 'Вокруг главного процессора собираются заражённые, защищая сигнал от любой попытки отключения.'),
         dilemma=('Право на существование', 'Система утверждает, что способна отвести орду от людей. Она просит доверия, но доказать искренность не может.',
                  ('Дать системе шанс', 'Ты сохраняешь опасный интеллект ради возможного спасения.', 'help'),
                  ('Забрать ключ отключения', 'Система не получит власти над судьбами выживших.', 'take'))),
    dict(key='dawn', title='После последнего рассвета', level=35, location='Красная пустошь', material='rare',
         intro='Перед тобой передатчик, способный изменить весь регион. Осталось решить, кто будет контролировать завтрашний день.',
         scout=('Последняя запись', 'В журнале осталась фраза исследовательницы: «Страшнее инфекции только люди, которым всё равно».'),
         fight=('Порог новой жизни', 'Последняя линия обороны башни поднимается из тени. Позади неё — рубильник и начало новой истории.'),
         dilemma=('Выбор будущего', 'Ты можешь передать технологии сети убежищ или запечатать башню и управлять безопасностью самостоятельно.',
                  ('Объединить убежища', 'Ты выбираешь сложный путь открытого сотрудничества.', 'help'),
                  ('Закрыть технологию', 'Ты выбираешь независимость и ответственность без союзников.', 'take'))),
]
assert len(CHAPTERS) == 10 and len({c['key'] for c in CHAPTERS}) == 10

class StoryProgress(Base):
    __tablename__ = 'story_progress'
    player_id = Column(BigInteger, ForeignKey('players.id'), primary_key=True)
    chapter = Column(Integer, nullable=False, default=0)
    stage = Column(Integer, nullable=False, default=0)
    trust = Column(Integer, nullable=False, default=0)
    decisions = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), default=now, nullable=False)


class StoryAct(BaseModel):
    action: str = Field(min_length=1, max_length=30)


def get_progress(db, pid):
    s = db.scalar(select(StoryProgress).where(StoryProgress.player_id == pid).with_for_update())
    if s is None:
        s = StoryProgress(player_id=pid, chapter=0, stage=0, trust=0, decisions=[])
        db.add(s)
        db.flush()
    return s


def story_view(p, s):
    finished = s.chapter >= len(CHAPTERS)
    chapter = None if finished else CHAPTERS[s.chapter]
    can_start = bool(chapter and p.level >= chapter['level'])
    statuses = [dict(key=c['key'], title=c['title'], level=c['level'],
                     status='completed' if i < s.chapter else ('current' if i == s.chapter else 'locked'))
                for i, c in enumerate(CHAPTERS)]
    scene = None
    if chapter:
        if s.stage == 0:
            name, body = chapter['scout']; scene = dict(kind='scout', title=name, text=body,
                                                       actions=[dict(key='scout', title='Исследовать местность', energy=max(3, 6+s.chapter//2-(2 if s.trust>=3 else 0)))])
        elif s.stage == 1:
            name, body = chapter['fight']; scene = dict(kind='combat', title=name, text=body,
                                                        actions=[dict(key='fight', title='Принять бой', energy=7+s.chapter)])
        else:
            name, body, good, hard = chapter['dilemma']
            scene = dict(kind='choice', title=name, text=body,
                         actions=[dict(key=good[2], title=good[0], description=good[1], energy=0),
                                  dict(key=hard[2], title=hard[0], description=hard[1], energy=0)])
    return dict(chapters=statuses, chapter_index=s.chapter + (0 if finished else 1),
                completed_count=min(s.chapter, len(CHAPTERS)), total=len(CHAPTERS),
                stage=s.stage, trust=s.trust, karma=p.karma, chapter_title=chapter['title'] if chapter else '',
                intro=chapter['intro'] if chapter else '', location=chapter['location'] if chapter else '',
                level_required=chapter['level'] if chapter else 0, available=can_start,
                scene=scene, finished=finished, ending=('Сеть убежищ' if s.trust >= 0 else 'Одинокая крепость') if finished else None,
                ending_text=('Зарождается союз поселений: рискованный, но открытый будущему.' if s.trust >= 0 else
                             'Ты превращаешь башню в автономную крепость: безопасную, но одинокую.') if finished else None,
                perk=('Поддержка союзников: −2 энергии за разведку' if s.trust>=3 else
                      'Контрабанда: больше крышек за сюжетные схватки' if s.trust<=-3 else
                      'Репутация нейтральная'),
                decisions=(s.decisions or [])[-10:])


def perform(db, p, s, action):
    if s.chapter >= len(CHAPTERS):
        raise ValueError('Кампания уже завершена')
    c = CHAPTERS[s.chapter]
    if p.level < c['level']:
        raise ValueError(f'Для главы «{c["title"]}» нужен уровень {c["level"]}')
    if db.scalar(select(Battle.id).where(Battle.player_id == p.id)):
        raise ValueError('Сначала закончи текущий бой с заражённым')
    chapter_no = s.chapter + 1
    if s.stage == 0:
        if action != 'scout':
            raise ValueError('Сначала проведи разведку')
        cost = max(3, 6+s.chapter//2-(2 if s.trust >= 3 else 0))
        spend_stamina(p, cost)
        qty = min(4, 1+s.chapter//3) + (1 if s.trust >= 3 else 0)
        give_item(db, p.id, c['material'], qty)
        gain_xp(p, 18+s.chapter*5)
        s.stage = 1
        msg = f'Найдены улики и {qty} ед. ресурсов. Разведка завершена.'
    elif s.stage == 1:
        if action != 'fight':
            raise ValueError('Сначала разберись с охраной')
        spend_stamina(p, 7+s.chapter)
        defense = 0
        try:
            from gear import gear_stats
            defense = max(0, gear_stats(db, p.id).get('defense', 0))
        except ImportError:
            pass
        damage = max(2, 8 + s.chapter*4 - defense - int(talent_bonus(p,'mitigation')*10)
                     - (min(4, s.trust//2) if s.trust >= 3 else 0))
        if p.hp <= damage:
            p.hp = 1
            msg = f'Атака отбита, но ты едва выжила. Восстанови HP и повтори попытку. Получен урон: {damage}.'
            return dict(message=msg, success=False, damage=damage, reward=None)
        p.hp -= damage
        p.kills += 1
        progress(db, p.id, 'kills')
        xp = 35+s.chapter*10
        gain_xp(p, xp)
        money = 13+s.chapter*6 + (20+s.chapter*5 if s.trust <= -3 else 0)
        p.caps += money
        s.stage = 2
        msg = f'Враг повержен! −{damage} HP, +{xp} XP, +{money} крышек.'
    else:
        if action not in ('help','take'):
            raise ValueError('Выбери один из двух путей')
        # Each act modifies one locked story row; a repeated request advances no extra chapters.
        if action == 'help':
            s.trust = min(10, s.trust+1)
            p.karma = min(100, p.karma+1)
            give_item(db, p.id, 'medkit', 1)
            choice_label = c['dilemma'][2][0]
            consequence = 'Союзники запомнили твою помощь. +1 аптечка.'
        else:
            s.trust = max(-10, s.trust-1)
            p.karma = max(-100, p.karma-1)
            bonus = 40+s.chapter*15
            p.caps += bonus
            choice_label = c['dilemma'][3][0]
            consequence = f'Ты берёшь дополнительные припасы: +{bonus} крышек.'
        xp = 95+s.chapter*40
        money = 65+s.chapter*20
        gain_xp(p,xp)
        p.caps += money
        if chapter_no >= 6:
            give_item(db, p.id, 'rare', 1 if chapter_no < 9 else 2)
        else:
            give_item(db, p.id, c['material'], 2)
        past = list(s.decisions or [])
        past.append(dict(chapter=chapter_no, title=c['title'], decision=choice_label, path=action))
        s.decisions = past[-10:]
        s.chapter += 1
        s.stage = 0
        msg = f'Глава {chapter_no} завершена! +{xp} XP, +{money} крышек. {consequence}'
    s.updated_at = now()
    return dict(message=msg,success=True,reward=action if action in ('help','take') else None)


def install_story(app, with_player, ready):
    router = APIRouter(prefix='/api/story', tags=['story'])
    def session():
        with SessionLocal() as db:
            yield db

    @router.get('')
    def get_story(request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request, db)
            s = get_progress(db,p.id)
            return story_view(p,s)

    @router.post('/act')
    def take_action(body: StoryAct, request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request,db)
            ready(p)
            s = get_progress(db,p.id)
            result = perform(db,p,s,body.action)
            result['story'] = story_view(p,s)
            return result
    app.include_router(router)