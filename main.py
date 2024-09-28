import os, ffmpeg, uuid, json, random, string, shutil
from datetime import datetime
from cached_property import cached_property

class Game:
    def __init__(self, name: str, folder_name: str, identifier: str):
        self.name = name
        self.folder_name = folder_name
        self.identifier = identifier
        self.path = os.path.join(INSTANCE.clips_path, folder_name)

class Fixer:
    def __init__(self) -> None:
        self._store_path = os.path.join(os.environ["AppData"], "Medal", "store")
        self._settings = self._load_store_file("settings.json")
        self._user_data = self._load_store_file("user.json")
        self._games = self._load_store_file("game.json")
        self._clips = self._load_store_file("clips.json")

        self.clips_path = os.path.join(self.base_path, "Clips")
        self.edits_path = os.path.join(self.base_path, "Edits")
        self.thumbnails_path = os.path.join(self.base_path, ".Thumbnails")

    @property
    def base_path(self) -> str:
        return self._settings["recorder"]["clipFolder"]
    
    @property
    def user_id(self) -> str:
        return self._user_data["userId"]
    
    @property
    def username(self) -> str:
        return self._user_data["userName"]
    
    @property
    def user_thumbnail(self) -> str:
        return self._user_data["thumbnail"]

    def _load_store_file(self, filename: str):
        with open(os.path.join(self._store_path, filename), "r", encoding="utf8") as f:
            return json.load(f)
    
    def get_game_from_folder(self, folder: str) -> Game:
        for game in self._games["games"]:
            folder_name = game["alternativeName"]
            for character in "\\/:*?\"<>|'":
                folder_name = folder_name.replace(character, "")
            if folder_name == folder:
                return Game(game["categoryName"], folder_name, game["categoryId"])
        return None
    
    def build_clips(self) -> dict:
        clips = {}
        processed = []
        for clip in self._clips.values():
            processed.append(clip["FilePath"])
            clips[clip["uuid"]] = clip
        for game_dir in os.listdir(self.clips_path):
            game = self.get_game_from_folder(game_dir)
            if game is None:
                continue
            for clip_file in os.listdir(game.path):
                if "_" in clip_file:
                    continue
                clip = Clip(clip_file, game)
                try:
                    if not clip.location.path in processed:
                        clips[str(clip.uuid)] = clip.build()
                        processed.append(clip.location.path)
                except:
                    continue
        return clips

class ClipLocation:
    def __init__(self, name: str, path: str, thumbnail_path: str):
        self.name = name
        self.path = path
        self.thumbnail_path = thumbnail_path

class Clip:
    def __init__(self, filename: str, game: Game):
        self._filename = filename
        self._probe_cache = {}
        self.game = game
        self.location = ClipLocation(
            self._filename[:-4],
            os.path.join(INSTANCE.clips_path, game.folder_name, self._filename),
            os.path.join(INSTANCE.thumbnails_path, self._filename[:-4] + ".jpg")
        )
        self.edit_location = self.find_edits()

        self.uuid = uuid.uuid4()
        self.identifier = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
        self.session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=14))

    @cached_property
    def timestamp(self) -> datetime:
        dt_string = self.location.name[len("MedalTV" + self.game.folder_name.replace(" ", "")):].split("-")[0]
        return datetime(
            year=int(dt_string[:4]),
            month=int(dt_string[4:6]),
            day=int(dt_string[6:8]),
            hour=int(dt_string[8:10]),
            minute=int(dt_string[10:12]),
            second=int(dt_string[12:14])
        )

    def find_edits(self):
        edit_location = None
        for edit_part in os.listdir(INSTANCE.edits_path):
            if not edit_part.startswith(self.location.name):
                continue
            temp_name = edit_part[:-4]
            if edit_location is None or len(temp_name) > len(edit_location.name):
                edit_location = ClipLocation(
                    temp_name,
                    os.path.join(INSTANCE.edits_path, temp_name + ".mp4"),
                    os.path.join(INSTANCE.edits_path, temp_name + ".jpg")
                )
        return edit_location

    def _probe(self, location: ClipLocation):
        path = location.path
        if path in self._probe_cache:
            return self._probe_cache[path]
        result = ffmpeg.probe(location.path)
        self._probe_cache[path] = result
        return result

    def _get_stream_of(self, type: str, probe: dict):
        for stream in probe["streams"]:
            if stream["codec_type"].lower() == type.lower():
                return stream
        return None

    def get_resolution(self) -> str:
        width = self._get_stream_of("video", self._probe(self.location))["coded_width"]
        if width == 2160:
            return "UHD"
        elif width == 1440:
            return "QHD"
        elif width == 720:
            return "HIGH"
        elif width == 640:
            return "MEDIUM"
        elif width == 480:
            return "LOW"
        else:
            return "FULL_HD"

    def build(self) -> dict:
        location = self.location if self.edit_location is None else self.edit_location
        probe = self._probe(location)
        return {
            "uuid": str(self.uuid),
            "clipID": self.identifier,
            "Status": "local",
            "FilePath": location.path,
            "Image": location.thumbnail_path,
            "SaveType": "1",
            "GameTitle": f"{self.game.name} {self.timestamp.strftime("%x %X")}",
            "TimeCreated": self.timestamp.timestamp(),
            "GameCategory": self.game.identifier,
            "Flag": 0,
            "clipType": "clip",
            "userId": INSTANCE.user_id,
            "metadata": self.build_medal_metadata(),
            "encoded": True,
            "fileSource": "medal",
            "contentType": 15,
            "isSkipThumbnail": False,
            "skipDraft": False,
            "sessionId": self.session_id,
            "Content": self.build_content_metadata(location),
            "origin": "Recorder",
            "duration": float(probe["format"]["duration"]),
            "ffmpegMetadata": self.build_ffmpeg_metadata(location),
            "Size": int(probe["format"]["size"]),
            "ExportKey": None,
            "thumbnailURL": None,
            "corruptionCheck": {
                "version": "1",
                "passed": True
            },
            "healthCheckTimestamp": datetime.now().timestamp()
        }
    
    def build_medal_metadata(self) -> dict:
        probe = self._probe(self.location)
        video_data = self._get_stream_of("video", probe)
        return {
            "eventobj": {
                "name": "",
                "tags": {},
                "data": {}
            },
            "triggerType": "Keyboard",
            "isGAO": False,
            "isUWP": False,
            "generateThumbnail": True,
            "clipDurationSec": int(float(probe["format"]["duration"])),
            "attributedCategoryId": None,
            "attributedCategoryName": None,
            "activeWindowTitle": None,
            "outputPath": None,
            "dontPublish": False,
            "alertType": 0,
            "quality": {
                "resolution": self.get_resolution(),
                "fps": eval(video_data["r_frame_rate"]),
                "bitrate": str(int(int(probe["format"]["bit_rate"]) / 1000000)) + "M",
            }
        }
    
    def build_content_metadata(self, location: ClipLocation) -> dict:
        video_data = self._get_stream_of("video", self._probe(location))
        return {
            "contentId": self.identifier,
            "contentType": 15,
            "categoryId": self.game.identifier,
            "privacy": 0,
            "hasTitle": False,
            "contentTitle": "Untitled",
            "contentDescription": "",
            "tags": [],
            "userTags": [],
            "recentComments": [],
            "music": [],
            "layers": [],
            "viewers": [],
            "hasTemplates": False,
            "client": "Electron",
            "clientVersion": "4.2521.0",
            "state": {
                "type": "draft",
                "isSuccess": True,
                "isShareable": False
            },
            "risk": 0,
            "unseenCount": 0,
            "sourceWidth": video_data["width"],
            "sourceHeight": video_data["height"],
            "videoLengthSeconds": float(video_data["duration"]),
            "parent": -1,
            "poster": INSTANCE._user_data,
            "contentPreview1080p": "",
            "contentPreview720p": "",
            "contentPreview480p": "",
            "contentPreview360p": "",
            "contentPreview240p": "",
            "contentPreview144p": "",
            "thumbnail1080p": "",
            "thumbnail720p": "",
            "thumbnail480p": "",
            "thumbnail360p": "",
            "thumbnail240p": "",
            "thumbnail144p": "",
            "thumbnailUrl": "",
            "contentShareUrl": None,
            "uniqueGuestViews": 0,
            "pinPosition": 0,
            "pinned": False,
            "supportMatchStats": False,
            "requireLogin": False,
            "created": self.timestamp.timestamp(),
            "publishedAt": None,
            "archivedAt": None,
            "urlsExpireAt": 1727544600000,
            "likes": 0,
            "views": 0,
            "comments": 0,
            "processed": 2,
            "shareCount": 0,
            "hasAccess": 1,
            "hasSound": 1,
            "useNativeDiscordEmbed": True,
            "orientation": "landscape",
            "matchUsers": [],
            "contentCollections": [],
            "userSaved": 0,
            "userLiked": 0,
            "userViewed": 1,
            "userViewedRecently": 1
        }

    def build_ffmpeg_metadata(self, location: ClipLocation) -> dict:
        probe = self._probe(location)
        video_data = self._get_stream_of("video", probe)
        audio_data = self._get_stream_of("audio", probe)
        return {
            "duration": probe["format"]["duration"],
            "bitrate": probe["format"]["bit_rate"],
            "contentStartTime": float(video_data["start_time"]),
            "video": {
                "codec": video_data["codec_name"],
                "colorspace": video_data["pix_fmt"],
                "bitrate": video_data["bit_rate"],
                "resolution": {
                    "width": video_data["width"],
                    "height": video_data["height"]
                },
                "aspectRatio": video_data["display_aspect_ratio"],
                "startTime": video_data["start_time"],
                "duration": video_data["duration"]
            },
            "audio": {
                "codec": audio_data["codec_name"],
                "bitrate": audio_data["bit_rate"],
                "samplerate": audio_data["sample_rate"],
                "startTime": audio_data["start_time"],
                "duration": audio_data["duration"]
            },
            "metadataVersion": "ffprobe.v1"
        }
    
INSTANCE = Fixer()

if __name__ == "__main__":
    clips_store_path = os.path.join(INSTANCE._store_path, "clips.json")
    shutil.copy(clips_store_path, os.path.join(INSTANCE._store_path, "clips (BACKUP).json"))
    with open(clips_store_path, "w") as f:
        json.dump(INSTANCE.build_clips(), f, indent=2)
