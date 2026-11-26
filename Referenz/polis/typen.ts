/* Options:
Date: 2026-11-26 15:36:07
Version: 5.80
Tip: To override a DTO option, remove "//" prefix before updating
BaseUrl: https://polisapi.media.int/v2

//GlobalNamespace: 
//AddServiceStackTypes: True
//AddResponseStatus: False
//AddImplicitVersion: 
//AddDescriptionAsComments: True
//IncludeTypes: 
//ExcludeTypes: 
//DefaultImports: 
*/


export interface IReturn<T>
{
    createResponse(): T;
}

export interface IReturnVoid
{
    createResponse(): void;
}

export enum Values
{
    Land = 1,
    Kanton = 2,
    Bezirk = 3,
    Gemeinde = 4,
    AuslandCh = 5,
    Stadtkreis = 6,
}

export enum Values
{
    Resultat = 3,
    Hochrechnung1 = 4,
    Web = 5,
    Trend = 6,
    Zwischenresultat = 7,
    Hochrechnung2 = 8,
    Hochrechnung3 = 9,
    FremdeHochrechnung = 10,
}

export enum ResultSortOption
{
    Default = 'Default',
    LeftRightPosition = 'LeftRightPosition',
}

// @Flags()
export enum ResultSelectionOption
{
    CandidateResults = 1,
    PartyResults = 2,
    MetaResults = 4,
    All = 7,
}

export enum language
{
    DE = 'DE',
    FR = 'FR',
    IT = 'IT',
    RM = 'RM',
    EN = 'EN',
}

// @DataContract
export class PolisBaseRequest implements IPolisRequest
{
    // @DataMember(Name="Auth_Key")
    public AuthKey: string;

    public constructor(init?: Partial<PolisBaseRequest>) { (Object as any).assign(this, init); }
}

// @DataContract
export class PolisBaseExportRequest extends PolisBaseRequest implements IPolisRequest
{

    public constructor(init?: Partial<PolisBaseExportRequest>) { super(init); (Object as any).assign(this, init); }
}

export interface IPolisRequest
{
    AuthKey: string;
}

export class OnAirType implements IEntity
{
    public Id: number;
    public Name: string;
    public ApiExport: boolean;
    public GUID: string;
    public OnAir: OnAir[];
    public Text: string;

    public constructor(init?: Partial<OnAirType>) { (Object as any).assign(this, init); }
}

export class PartyCandidacy implements IEntity, IDeletingInfo
{
    public Id: number;
    public ElectionId: number;
    public PartyId: number;
    public LocationId: number;
    public SortOrder: number;
    public GUID: string;
    public Party: Party;
    public Result: Result[];
    public Location: Location;
    public Election: Election;
    public Text: string;
    public ParentTableName: string;
    public ParentId: number;

    public constructor(init?: Partial<PartyCandidacy>) { (Object as any).assign(this, init); }
}

export class VizParty implements IEntity
{
    public Id: number;
    public PartyId: number;
    public Color1: string;
    public Color2: string;
    public Color3: string;
    public ColorHex: string;
    public HrKey: string;
    public LeftRightAllocation: number;
    public VizColorDiffuse: string;
    public VizColorEmission: string;
    public VizColorSpecular: string;
    public VizColorAmbient: string;
    public CouncilAllocation: number;
    public CouncilAllocationWeb: number;
    public GUID: string;
    public Party: Party;
    public Text: string;

    public constructor(init?: Partial<VizParty>) { (Object as any).assign(this, init); }
}

export class Translation implements ITranslation, IEntity
{
    public Id: number;
    public De: string;
    public Fr: string;
    public It: string;
    public Rm: string;
    public En: string;
    public GUID: string;
    public Image: Image[];
    public VotingImageDescription: Voting[];
    public VotingName: Voting[];
    public Party: Party[];
    public Case: Case[];
    public Party2: Party[];
    public Party21: Party[];
    public Image1: Image[];
    public Voting2: Voting[];
    public Text: string;

    public constructor(init?: Partial<Translation>) { (Object as any).assign(this, init); }
}

export class CommentDetail implements IEntity, IDeletingInfo
{
    public Id: number;
    public CommentId: number;
    public Text: string;
    public GUID: string;
    public Comment: Comment;
    public ParentTableName: string;
    public ParentId: number;

    public constructor(init?: Partial<CommentDetail>) { (Object as any).assign(this, init); }
}

export class Seat implements IEntity
{
    public Id: number;
    public OfficialId: number;
    public LocationId: number;
    public Amount: number;
    public GUID: string;
    public ElectionId: number;
    public Official: Official;
    public Location: Location;
    public Election: Election;
    public Text: string;

    public constructor(init?: Partial<Seat>) { (Object as any).assign(this, init); }
}

export class OfficialType implements IEntity
{
    public Id: number;
    public Name: string;
    public GUID: string;
    public Official: Official[];
    public Text: string;

    public constructor(init?: Partial<OfficialType>) { (Object as any).assign(this, init); }
}

export class Official implements IEntity
{
    public Id: number;
    public OfficialTypeId: number;
    public LocationId: number;
    public Name: string;
    public GUID: string;
    public CommentId: number;
    public Seat: Seat[];
    public OfficialType: OfficialType;
    public Location: Location;
    public Comment: Comment;
    public Election: Election[];
    public Text: string;

    public constructor(init?: Partial<Official>) { (Object as any).assign(this, init); }
}

export class Comment implements IEntity
{
    public Id: number;
    public GUID: string;
    public CommentDetail: CommentDetail[];
    public Voting: Voting[];
    public Candidate: Candidate[];
    public Party: Party[];
    public Official: Official[];
    public Election: Election[];
    public Text: string;

    public constructor(init?: Partial<Comment>) { (Object as any).assign(this, init); }
}

export class Party implements IEntity
{
    public Id: number;
    public LocationId: number;
    public ParentPartyId: number;
    public NameTranslationId: number;
    public ShortNameTranslationId: number;
    public LogoImageId: number;
    public SmartVoteId: number;
    public AdminName: string;
    public ProjectionKey: string;
    public ColorHex: string;
    public LeftRightAllocation: number;
    public CouncilAllocation: number;
    public CouncilAllocationWeb: number;
    public GUID: string;
    public HomepageTranslationId: number;
    public CommentId: number;
    public VizrtKey: string;
    public AdminId: number;
    public Candidate: Candidate[];
    public Image: Image;
    public PartyChildren: Party[];
    public PartyParent: Party;
    public PartyCandidacy: PartyCandidacy[];
    public VizParty: VizParty[];
    public TranslationName: Translation;
    public TranslationHomepage: Translation;
    public TranslationShortName: Translation;
    public Comment: Comment;
    public Location: Location;
    public Text: string;

    public constructor(init?: Partial<Party>) { (Object as any).assign(this, init); }
}

export class SmartVotePoliticalOffice implements IEntity
{
    public Id: number;
    public SmartVoteCandidateId: number;
    public Start: string;
    public End: string;
    public Mandate: string;
    public GUID: string;
    public SmartVoteCandidate: SmartVoteCandidate;
    public Text: string;

    public constructor(init?: Partial<SmartVotePoliticalOffice>) { (Object as any).assign(this, init); }
}

export class SmartVoteCandidate implements IDeletingInfo, IEntity
{
    public ParentTableName: string;
    public ParentId: number;
    public Id: number;
    public CandidateId: number;
    public SpiderImageId: number;
    public SmartVoteId: number;
    public Updated: string;
    public Canton: string;
    public Country: string;
    public Language: string;
    public CivilState: string;
    public Education: string;
    public Denomination: string;
    public Nationality: string;
    public Address: string;
    public Zip: string;
    public City: string;
    public ProfessionLearned: string;
    public ProfessionToday: string;
    public InterestBook: string;
    public InterestHobby: string;
    public InterestMovie: string;
    public InterestMusic: string;
    public Club: string;
    public CommitmentOther: string;
    public Children: number;
    public ProfileUrl: string;
    public PartyShort: string;
    public PersonalWebsite: string;
    public GUID: string;
    public Image: Image;
    public SmartVotePoliticalOffice: SmartVotePoliticalOffice[];
    public Candidate: Candidate;
    public Text: string;

    public constructor(init?: Partial<SmartVoteCandidate>) { (Object as any).assign(this, init); }
}

export class Candidate implements IEntity
{
    public Id: number;
    public PartyId: number;
    public LocationId: number;
    public OriginalImageId: number;
    public Firstname: string;
    public Lastname: string;
    public Sex: string;
    public Born: number;
    public Domicile: string;
    public ImportFix: boolean;
    public GUID: string;
    public CommentId: number;
    public Candidacy: Candidacy[];
    public OriginalImage: Image;
    public Party: Party;
    public Comment: Comment;
    public SmartVoteCandidate: SmartVoteCandidate[];
    public Location: Location;
    public Text: string;

    public constructor(init?: Partial<Candidate>) { (Object as any).assign(this, init); }
}

export class Image implements IEntity
{
    public Id: number;
    public TranslationId: number;
    public Name: string;
    public GUID: string;
    public ExtTranslationId: number;
    public ExtName: string;
    public Candidate: Candidate[];
    public Party: Party[];
    public SmartVoteCandidate: SmartVoteCandidate[];
    public Voting: Voting[];
    public Translation: Translation;
    public Location: Location[];
    public Translation1: Translation;
    public Text: string;

    public constructor(init?: Partial<Image>) { (Object as any).assign(this, init); }
}

export class VotingTopic implements IEntity
{
    public Id: number;
    public Name: string;
    public Visible: boolean;
    public GUID: string;
    public Voting: Voting[];
    public Text: string;

    public constructor(init?: Partial<VotingTopic>) { (Object as any).assign(this, init); }
}

export class VotingType implements IEntity
{
    public Id: number;
    public Name: string;
    public ShortName: string;
    public DoubleMajority: boolean;
    public GUID: string;
    public Voting: Voting[];
    public Text: string;

    public constructor(init?: Partial<VotingType>) { (Object as any).assign(this, init); }
}

export class LiveTickerMessageDoubleMajorityType implements IEntity
{
    public Id: number;
    public Name: string;
    public Description: string;
    public GUID: string;
    public LiveTickerMessage: LiveTickerMessage[];
    public Text: string;

    public constructor(init?: Partial<LiveTickerMessageDoubleMajorityType>) { (Object as any).assign(this, init); }
}

export class LiveTickerMessage implements IEntity
{
    public Id: number;
    public VotingId: number;
    public ElectionId: number;
    public Title: string;
    public Message: string;
    public Created: string;
    public Updated: string;
    public Changed: string;
    public GUID: string;
    public SubLocationId: number;
    public DoubleMajorityTypeId: number;
    public Election: Election;
    public Voting: Voting;
    public Location: Location;
    public LiveTickerMessageDoubleMajorityType: LiveTickerMessageDoubleMajorityType;
    public Text: string;

    public constructor(init?: Partial<LiveTickerMessage>) { (Object as any).assign(this, init); }
}

export class ResultImportLog implements IEntity
{
    public Id: number;
    public Date: string;
    public Level: string;
    public Message: string;
    public ElectionImportType: number;
    public LocationId: number;
    public ElectionId: number;
    public VotingId: number;
    public Location: Location;
    public Election: Election;
    public Voting: Voting;
    public Text: string;

    public constructor(init?: Partial<ResultImportLog>) { (Object as any).assign(this, init); }
}

export class Voting implements IEntity
{
    public Id: number;
    public LocationId: number;
    public NameTranslationId: number;
    public ImageDescriptionTranslationId: number;
    public SymbolImageId: number;
    public GUID: string;
    public CommentId: number;
    public CaseId: number;
    public VotingTypeId: number;
    public VotingTopicId: number;
    public AdminId: string;
    public SortOrder: number;
    public AutoImportBlocked: boolean;
    public ShortNameTranslationId: number;
    public Image: Image;
    public Result: Result[];
    public Case: Case;
    public VotingTopic: VotingTopic;
    public VotingType: VotingType;
    public TranslationImageDescription: Translation;
    public TranslationName: Translation;
    public Comment: Comment;
    public Location: Location;
    public LiveTickerMessage: LiveTickerMessage[];
    public ResultImportLog: ResultImportLog[];
    public TranslationShortName: Translation;
    public Text: string;

    public constructor(init?: Partial<Voting>) { (Object as any).assign(this, init); }
}

export class CaseExtension implements IEntity
{
    public RelativeTurnout: number;
    public TurnoutLocked: boolean;
    public LastUpdate: string;
    public DataConditionId: number;
    public Id: number;
    public CaseId: number;
    public TurnoutTolerance: string;
    public Case: Case;
    public DataCondition: DataCondition;
    public Text: string;

    public constructor(init?: Partial<CaseExtension>) { (Object as any).assign(this, init); }
}

export class Case implements IEntity, IGridModelItem
{
    public Id: number;
    public Date: string;
    public Active: boolean;
    public GUID: string;
    public TopicTranslationId: number;
    public NationalUrl: string;
    public KantonalUrl: string;
    public Voting: Voting[];
    public Translation: Translation;
    public Election: Election[];
    public CaseExtension: CaseExtension[];
    public Text: string;
    public Topic: string;

    public constructor(init?: Partial<Case>) { (Object as any).assign(this, init); }
}

export class ElectionRound implements IEntity
{
    public Id: number;
    public ParentElectionRoundId: number;
    public Name: string;
    public GUID: string;
    public ElectionToElectionRound: ElectionToElectionRound[];
    public ElectionRound1: ElectionRound[];
    public ElectionRound2: ElectionRound;
    public Text: string;

    public constructor(init?: Partial<ElectionRound>) { (Object as any).assign(this, init); }
}

export class ElectionToElectionRound implements IEntity
{
    public Id: number;
    public ElectionId: number;
    public ElectionRoundId: number;
    public PreviousElectionId: number;
    public GUID: string;
    public ElectionRound: ElectionRound;
    public Election: Election;
    public Election1: Election;
    public Text: string;

    public constructor(init?: Partial<ElectionToElectionRound>) { (Object as any).assign(this, init); }
}

export class SmartVoteElection implements IEntity
{
    public Id: number;
    public SmartVoteId: number;
    public ElectionGroupId: number;
    public Type: number;
    public ElectionDate: string;
    public Location: string;
    public Name: string;
    public CreatedAt: string;
    public UpdatedAt: string;
    public PublicationDateCandidates: string;
    public PublicationDateVoters: string;
    public Status: string;
    public Languages: string;
    public Election: Election[];
    public SmartVoteElection1: SmartVoteElection;
    public SmartVoteElection2: SmartVoteElection;
    public Text: string;

    public constructor(init?: Partial<SmartVoteElection>) { (Object as any).assign(this, init); }
}

export class Election implements IEntity
{
    public Id: number;
    public CaseId: number;
    public OfficialId: number;
    public CommentId: number;
    public GUID: string;
    public SortOrder: number;
    public CompareElectionId: number;
    public AutoImportBlocked: boolean;
    public SmartVoteElectionId: number;
    public Candidacy: Candidacy[];
    public Case: Case;
    public Comment: Comment;
    public ElectionToElectionRound: ElectionToElectionRound[];
    public OnAir: OnAir[];
    public PartyCandidacy: PartyCandidacy[];
    public Result: Result[];
    public Seat: Seat[];
    public ElectionToElectionRound1: ElectionToElectionRound[];
    public Official: Official;
    public LiveTickerMessage: LiveTickerMessage[];
    public Election1: Election[];
    public Election2: Election;
    public SmartVoteElection: SmartVoteElection;
    public ResultImportLog: ResultImportLog[];
    public Text: string;

    public constructor(init?: Partial<Election>) { (Object as any).assign(this, init); }
}

export class OnAir implements IEntity
{
    public Id: number;
    public OnAirTypeId: number;
    public ElectionId: number;
    public LocationId: number;
    public DataConditionId: number;
    public Message: string;
    public Created: string;
    public Updated: string;
    public GUID: string;
    public Changed: string;
    public DataCondition: DataCondition;
    public OnAirType: OnAirType;
    public Location: Location;
    public Election: Election;
    public Text: string;

    public constructor(init?: Partial<OnAir>) { (Object as any).assign(this, init); }
}

export class DataCondition implements IEntity
{
    public Id: number;
    public Name: string;
    public SortOrder: number;
    public Holdback: string;
    public GUID: string;
    public OnAir: OnAir[];
    public Result: Result[];
    public CaseExtension: CaseExtension[];
    public Text: string;
    public Translations: Func<DataCondition,string>[];

    public constructor(init?: Partial<DataCondition>) { (Object as any).assign(this, init); }
}

export class ResultCondition implements IEntity
{
    public Id: number;
    public Name: string;
    public IsElection: boolean;
    public SortOrder: number;
    public GUID: string;
    public Result: Result[];
    public Text: string;

    public constructor(init?: Partial<ResultCondition>) { (Object as any).assign(this, init); }
}

export class Trend implements IEntity
{
    public Id: number;
    public Name: string;
    public Value: number;
    public GUID: string;
    public Result: Result[];
    public Text: string;

    public constructor(init?: Partial<Trend>) { (Object as any).assign(this, init); }
}

export class ResultExtension implements IEntity
{
    public ResultId: number;
    public Tolerance: string;
    public Id: number;
    public Result: Result;
    public Text: string;

    public constructor(init?: Partial<ResultExtension>) { (Object as any).assign(this, init); }
}

export class Result
{
    public Message: string;

    public constructor(init?: Partial<Result>) { (Object as any).assign(this, init); }
}

export class Candidacy implements IEntity, IDeletingInfo
{
    public Id: number;
    public CandidateId: number;
    public ElectionId: number;
    public LocationId: number;
    public IsYet: boolean;
    public GUID: string;
    public Result: Result[];
    public Candidate: Candidate;
    public Location: Location;
    public Election: Election;
    public Text: string;
    public ParentTableName: string;
    public ParentId: number;

    public constructor(init?: Partial<Candidacy>) { (Object as any).assign(this, init); }
}

export class ConstituencyAllocation implements IEntity
{
    public Id: number;
    public ConstituencyId: number;
    public LocationId: number;
    public GUID: string;
    public Constituency: Constituency;
    public Location: Location;
    public Text: string;

    public constructor(init?: Partial<ConstituencyAllocation>) { (Object as any).assign(this, init); }
}

export class Constituency implements IEntity
{
    public Id: number;
    public LocationId: number;
    public Start: string;
    public End: string;
    public GUID: string;
    public ConstituencyAllocation: ConstituencyAllocation[];
    public Location: Location;
    public Text: string;

    public constructor(init?: Partial<Constituency>) { (Object as any).assign(this, init); }
}

export class Location implements IEntity
{
    public Id: number;
    public LocationTypeId: number;
    public ArmsImageId: number;
    public Name: string;
    public CapitalCity: string;
    public ShortName: string;
    public VotingStrength: number;
    public AdminId: number;
    public ImageBackground: string;
    public LastUpdate: string;
    public ImportName: string;
    public VectorData: string;
    public Url: string;
    public GUID: string;
    public Updated: boolean;
    public SmartVoteId: number;
    public Candidacy: Candidacy[];
    public Candidate: Candidate[];
    public Constituency: Constituency[];
    public ConstituencyAllocation: ConstituencyAllocation[];
    public Image: Image;
    public Voting: Voting[];
    public Official: Official[];
    public OnAir: OnAir[];
    public Party: Party[];
    public PartyCandidacy: PartyCandidacy[];
    public Result: Result[];
    public Seat: Seat[];
    public LocationType: LocationType;
    public LiveTickerMessage: LiveTickerMessage[];
    public ResultImportLog: ResultImportLog[];
    public Text: string;

    public constructor(init?: Partial<Location>) { (Object as any).assign(this, init); }
}

export class LocationType implements IEntity
{
    public Id: number;
    public ParentLocationTypeId: number;
    public Name: string;
    public SortOrder: number;
    public GUID: string;
    public LocationType1: LocationType[];
    public LocationType2: LocationType;
    public Location: Location[];
    public Text: string;

    public constructor(init?: Partial<LocationType>) { (Object as any).assign(this, init); }
}

export interface IEntity
{
    Id: number;
    Text: string;
}

export class Result implements IEntity
{
    public Id: number;
    public DataConditionId: number;
    public LocationId: number;
    public ResultConditionId: number;
    public VotingId: number;
    public TrendId: number;
    public ElectionId: number;
    public CandidacyId: number;
    public PartyCandidacyId: number;
    public VotingAbsoluteYes: number;
    public VotingAbsoluteNo: number;
    public VotingRelativeYes: number;
    public VotingRelativeNo: number;
    public VotingTotalCount: number;
    public VotingValidCount: number;
    public VotingRelativeTurnout: number;
    public VotingAbsoluteEligibleVoters: number;
    public ElectionAbsoluteSeatCount: number;
    public ElectionAbsoluteResult: number;
    public ElectionRelativeResult: number;
    public ElectionAbsoluteMajority: number;
    public ElectionSecondBallot: boolean;
    public CountedCommunities: number;
    public TotalCommunities: number;
    public Comment: string;
    public ExtendedComment: string;
    public Title: string;
    public Created: string;
    public LastUpdate: string;
    public Locked: boolean;
    public GUID: string;
    public VotingDoubleMajorityAbsoluteYes: number;
    public VotingDoubleMajorityAbsoluteNo: number;
    public Candidacy: Candidacy;
    public DataCondition: DataCondition;
    public PartyCandidacy: PartyCandidacy;
    public Voting: Voting;
    public ResultCondition: ResultCondition;
    public Trend: Trend;
    public Location: Location;
    public Election: Election;
    public ResultExtension: ResultExtension;
    public Text: string;

    public constructor(init?: Partial<Result>) { (Object as any).assign(this, init); }
}

export interface IDeletingInfo
{
    ParentTableName: string;
    ParentId: number;
}

export interface IGridModelItem
{
    Id: number;
}

export interface ITranslation
{
    De: string;
    Fr: string;
    It: string;
    Rm: string;
    En: string;
}

// @Route("/Polis.Elections", "GET")
export class GetElectionResults extends PolisBaseExportRequest implements IPolisRequest
{
    public CaseId: number;
    public ElectionId: number;
    public LocationId: number;
    public LocationTypeId: Values;
    public DataConditionId: Values;
    public Party: string;
    public Timestamp: string;
    public SortBy: ResultSortOption;
    public SelectOnly: ResultSelectionOption;
    public ShowEmptyResult: boolean;
    public OnlyChangeDates: boolean;

    public constructor(init?: Partial<GetElectionResults>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Official", "GET")
export class GetOfficial extends PolisBaseExportRequest implements IPolisRequest
{
    public OfficialId: number;
    public ElectionId: number;

    public constructor(init?: Partial<GetOfficial>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Locations", "GET")
export class GetLocation extends PolisBaseExportRequest implements IPolisRequest
{
    public LocationId: number;
    public ParentId: number;
    public Date: string;
    public Type: Values;

    public constructor(init?: Partial<GetLocation>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Cases")
export class GetCase extends PolisBaseExportRequest implements IPolisRequest
{
    public CaseId: number;
    public Date: string;
    public ListAllCases: boolean;
    public CasesNewerThan: string;

    public constructor(init?: Partial<GetCase>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Parties", "GET")
export class GetParty extends PolisBaseExportRequest implements IPolisRequest
{
    public PartyId: number;
    public LocationId: number;
    public ElectionId: number;

    public constructor(init?: Partial<GetParty>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Candidates", "GET")
export class GetCandidates extends PolisBaseExportRequest implements IPolisRequest
{
    public CandidateId: number;
    public PartyId: number;
    public ElectionId: number;
    public LocationId: number;

    public constructor(init?: Partial<GetCandidates>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.DataConditions")
export class GetDataCondition extends PolisBaseExportRequest implements IPolisRequest
{

    public constructor(init?: Partial<GetDataCondition>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Votations", "GET")
export class GetVotation extends PolisBaseExportRequest implements IPolisRequest
{
    public CaseId: number;
    public VotationId: number;
    public LocationId: number;
    public LocationTypeId: Values[];
    public VoteLocationId: number;
    public VoteLocationTypeId: Values;
    public DataConditionId: Values;
    public Timestamp: string;

    public constructor(init?: Partial<GetVotation>) { super(init); (Object as any).assign(this, init); }
}

// @Route("/Polis.Admin/FlushLocalization")
export class FlushCache extends PolisBaseRequest implements IReturn<Result>, IPolisRequest
{

    public constructor(init?: Partial<FlushCache>) { super(init); (Object as any).assign(this, init); }
    public createResponse() { return new Result(); }
    public getTypeName() { return 'FlushCache'; }
}

// @Route("/Polis.Admin/FlushETag")
export class FlushETag extends PolisBaseRequest implements IReturn<Result>, IPolisRequest
{

    public constructor(init?: Partial<FlushETag>) { super(init); (Object as any).assign(this, init); }
    public createResponse() { return new Result(); }
    public getTypeName() { return 'FlushETag'; }
}

// @Route("/Polis.Admin/FlushData")
export class FlushData extends PolisBaseRequest implements IReturn<Result>, IPolisRequest
{

    public constructor(init?: Partial<FlushData>) { super(init); (Object as any).assign(this, init); }
    public createResponse() { return new Result(); }
    public getTypeName() { return 'FlushData'; }
}

// @Route("/Polis.Admin/EnableCache")
export class EnableCache extends PolisBaseRequest implements IReturn<Result>, IPolisRequest
{

    public constructor(init?: Partial<EnableCache>) { super(init); (Object as any).assign(this, init); }
    public createResponse() { return new Result(); }
    public getTypeName() { return 'EnableCache'; }
}

// @Route("/Polis.Admin/DisableCache")
export class DisableCache extends PolisBaseRequest implements IReturn<Result>, IPolisRequest
{

    public constructor(init?: Partial<DisableCache>) { super(init); (Object as any).assign(this, init); }
    public createResponse() { return new Result(); }
    public getTypeName() { return 'DisableCache'; }
}

