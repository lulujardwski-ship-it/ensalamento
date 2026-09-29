// Ensalamento: explicit constraint checks and deterministic greedy allocation.
// nlohmann/json is used solely to read/write JSON; it does not solve allocation.
#include <nlohmann/json.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
namespace {
constexpr std::size_t MAX_INPUT = 8 * 1024 * 1024;
struct InputError : std::runtime_error { using std::runtime_error::runtime_error; };
void require(bool b, const std::string& text) { if (!b) throw InputError(text); }
std::string str(const json& j, const char* key, const std::string& fallback = "") {
    if (!j.contains(key) || j.at(key).is_null()) return fallback;
    require(j.at(key).is_string(), std::string(key) + ": deve ser texto.");
    auto s = j.at(key).get<std::string>();
    require(s.size() <= 2000, std::string(key) + ": texto muito longo.");
    return s;
}
std::string id(const json& j, const char* key = "id") {
    auto s = str(j, key); require(!s.empty() && s.size() <= 128, std::string(key) + ": identificador obrigatório (até 128 caracteres)."); return s;
}
int integer(const json& j, const char* key, int fallback, int low, int high) {
    if (!j.contains(key) || j.at(key).is_null()) return fallback;
    require(j.at(key).is_number_integer(), std::string(key) + ": deve ser inteiro.");
    auto x = j.at(key).get<std::int64_t>();
    require(x >= low && x <= high, std::string(key) + ": valor fora do intervalo permitido.");
    return static_cast<int>(x);
}
bool boolean(const json& j, const char* key, bool fallback = false) {
    if (!j.contains(key) || j.at(key).is_null()) return fallback;
    require(j.at(key).is_boolean(), std::string(key) + ": deve ser booleano."); return j.at(key).get<bool>();
}
const json& array(const json& j, const char* key, std::size_t limit, bool mandatory = false) {
    static const json empty = json::array();
    if (!j.contains(key)) { require(!mandatory, std::string(key) + ": lista obrigatória."); return empty; }
    const auto& a = j.at(key); require(a.is_array() && a.size() <= limit, std::string(key) + ": lista inválida ou acima do limite."); return a;
}
std::set<std::string> strings(const json& j, const char* key, bool lower = false) {
    std::set<std::string> result;
    for (const auto& x : array(j, key, 400)) {
        require(x.is_string(), std::string(key) + ": valores devem ser textos.");
        auto s = x.get<std::string>(); require(!s.empty() && s.size() <= 254, std::string(key) + ": valor inválido.");
        if (lower) std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){return std::tolower(c);});
        result.insert(s);
    }
    return result;
}
int timeOf(const std::string& s) {
    require(s.size() == 5 && s[2] == ':' && std::isdigit(static_cast<unsigned char>(s[0])) && std::isdigit(static_cast<unsigned char>(s[1])) && std::isdigit(static_cast<unsigned char>(s[3])) && std::isdigit(static_cast<unsigned char>(s[4])), "Horário deve usar HH:MM.");
    int h=(s[0]-'0')*10+s[1]-'0', m=(s[3]-'0')*10+s[4]-'0';
    require(h < 24 && m < 60, "Horário inválido."); return h*60+m;
}
// Gregorian calendar converted to a day ordinal; 1970-01-01 is day zero.
// Derivation: Howard Hinnant, https://howardhinnant.github.io/date_algorithms.html
int dayOf(const std::string& s) {
    require(s.size()==10 && s[4]=='-' && s[7]=='-', "Data deve usar AAAA-MM-DD.");
    for (int p : {0,1,2,3,5,6,8,9}) require(std::isdigit(static_cast<unsigned char>(s[p])), "Data inválida.");
    int y=std::stoi(s.substr(0,4)), m=std::stoi(s.substr(5,2)), d=std::stoi(s.substr(8,2));
    require(y>=1970 && y<=2100 && m>=1 && m<=12, "Data fora do intervalo 1970–2100.");
    int lengths[]={31,28,31,30,31,30,31,31,30,31,30,31};
    if (y%4==0 && (y%100!=0 || y%400==0)) lengths[1]=29;
    require(d>=1 && d<=lengths[m-1], "Dia inexistente no calendário.");
    y -= m <= 2; int era=y/400; unsigned yo=static_cast<unsigned>(y-era*400);
    unsigned doy=(153*(m+(m>2?-3:9))+2)/5+d-1;
    return era*146097+static_cast<int>(yo*365+yo/4-yo/100+doy)-719468;
}
int weekday(int day) { return (day+3)%7; } // Monday=0, epoch Thursday=3.
struct Schedule {
    int first=0,last=0,week=-1,start=0,end=0;
    std::set<int> excluded;
    bool on(int d) const { return d>=first && d<=last && (week<0 || weekday(d)==week) && !excluded.count(d); }
};
Schedule schedule(const json& j, bool exclusions = true) {
    require(j.is_object(), "Encontro/indisponibilidade deve ser objeto.");
    Schedule s; s.start=timeOf(str(j,"start")); s.end=timeOf(str(j,"end"));
    require(s.end>s.start, "Horário final deve ser posterior ao inicial; divida encontros que atravessam meia-noite.");
    auto date=str(j,"date");
    if (!date.empty()) s.first=s.last=dayOf(date);
    else {
        s.week=integer(j,"weekday",-1,0,6); require(s.week>=0,"weekday obrigatório para recorrência (0=segunda, 6=domingo).");
        s.first=dayOf(str(j,"start_date")); s.last=dayOf(str(j,"end_date"));
        require(s.last>=s.first && s.last-s.first<=1830,"Recorrência deve ter datas ordenadas e duração máxima de cinco anos.");
    }
    if (exclusions) for (const auto& x:array(j,"excluded_dates",400)) { require(x.is_string(),"excluded_dates deve conter datas."); s.excluded.insert(dayOf(x.get<std::string>())); }
    int d=s.first; if (s.week>=0) d+=(s.week-weekday(d)+7)%7;
    bool exists=false; for (;d<=s.last;d+=s.week<0?1:7) if(s.on(d)) {exists=true;break;}
    require(exists,"Encontro sem nenhuma ocorrência válida no intervalo informado.");
    return s;
}
bool overlap(const Schedule& a,const Schedule& b) {
    if (a.start>=b.end || b.start>=a.end) return false; // Half-open intervals.
    int lo=std::max(a.first,b.first), hi=std::min(a.last,b.last); if(lo>hi)return false;
    if(a.week<0)return b.on(a.first) && a.on(a.first);
    if(b.week<0)return a.on(b.first) && b.on(b.first);
    if(a.week!=b.week)return false;
    lo+=(a.week-weekday(lo)+7)%7;
    for(int d=lo;d<=hi;d+=7)if(a.on(d)&&b.on(d))return true;
    return false;
}
struct Room {std::string id,name,campus,building,status;int capacity;bool accessible;std::set<std::string> resources;std::vector<Schedule> available,unavailable;};
struct Class {std::string id,campus,building,status;int size;bool accessibility,active;std::set<std::string> required,preferred,teachers;};
struct Meeting {std::string id,classId;int ci;Schedule when;};
struct Allocation {std::string meeting,room;bool locked;json value;};
struct Reason {std::string code,message;};
struct Candidate {int room;double score;std::string explanation;json details;};
class Engine {
    std::vector<Room> rooms; std::vector<Class> classes; std::vector<Meeting> meetings;
    std::map<std::string,int> ri,ci,mi;
    std::vector<Allocation> original,allocations;
    std::map<std::string,std::vector<Reason>> academic;
    std::map<std::string,double> weights{{"capacity",40},{"building",20},{"resources",25},{"stability",15}};
    std::size_t evaluations=0;
    void unique(std::map<std::string,int>& index,const std::string& key,int pos,const char* name) { require(index.emplace(key,pos).second,std::string(name)+": id duplicado "+key); }
    bool active(const Meeting& m)const{return classes[m.ci].active;}
    static bool intersects(const std::set<std::string>& a,const std::set<std::string>& b) {for(const auto& x:a)if(b.count(x))return true;return false;}
    static bool withinAvailability(const Schedule& meeting,const std::vector<Schedule>& windows) {
        if(windows.empty())return true;
        int first=meeting.first;
        if(meeting.week>=0)first+=(meeting.week-weekday(first)+7)%7;
        // On every actual meeting date, merge intersecting/adjacent opening windows.
        for(int day=first;day<=meeting.last;day+=meeting.week<0?1:7) {
            if(!meeting.on(day))continue;
            std::vector<std::pair<int,int>> intervals;
            for(const auto& window:windows)if(window.on(day))intervals.push_back({window.start,window.end});
            std::sort(intervals.begin(),intervals.end());
            int coveredUntil=meeting.start;
            for(const auto& interval:intervals) {
                if(interval.second<=coveredUntil)continue;
                if(interval.first>coveredUntil)break;
                coveredUntil=interval.second;
                if(coveredUntil>=meeting.end)break;
            }
            if(coveredUntil<meeting.end)return false;
        }
        return true;
    }
    std::vector<Reason> checks(const Meeting& m,const Room& r,const std::vector<Allocation>& occupied,bool dynamic=true) {
        ++evaluations;const auto& c=classes[m.ci];std::vector<Reason> reasons;
        auto add=[&](const char* code,const std::string& text){reasons.push_back({code,text});};
        if(!c.active)add("CLASS_INACTIVE","Turma cancelada ou encerrada.");
        if(r.status!="active")add("ROOM_INACTIVE","Sala em manutenção ou desativada.");
        if(r.capacity<c.size)add("CAPACITY","Capacidade insuficiente ("+std::to_string(r.capacity)+" < "+std::to_string(c.size)+").");
        if(r.campus!=c.campus)add("CAMPUS","Sala em campus diferente do solicitado.");
        if(c.accessibility&&!r.accessible)add("ACCESSIBILITY","Sala não atende à acessibilidade obrigatória.");
        for(const auto& resource:c.required)if(!r.resources.count(resource))add("RESOURCE","Recurso obrigatório ausente: "+resource+".");
        if(!withinAvailability(m.when,r.available))add("OUTSIDE_AVAILABILITY","Uma ou mais ocorrências não estão inteiramente cobertas pelos intervalos de disponibilidade da sala.");
        for(const auto& u:r.unavailable)if(overlap(m.when,u)){add("UNAVAILABLE","Sala indisponível em uma ou mais ocorrências do encontro.");break;}
        if(dynamic) {
            auto ac=academic.find(m.id);if(ac!=academic.end())reasons.insert(reasons.end(),ac->second.begin(),ac->second.end());
            for(const auto& a:occupied) {
                if(a.meeting==m.id||a.room!=r.id)continue;
                auto it=mi.find(a.meeting);if(it==mi.end())continue;
                const auto& other=meetings[it->second];
                if(active(other)&&overlap(m.when,other.when)) {add("ROOM_OVERLAP","Sala ocupada pelo encontro "+other.id+" em horário sobreposto.");}
            }
        }
        return reasons;
    }
    Candidate scored(const Meeting& m,int roomIndex,const std::vector<Allocation>& occupied)const {
        const auto& r=rooms[roomIndex];const auto& c=classes[m.ci];
        double capacity=static_cast<double>(c.size)/r.capacity,building=c.building.empty()||r.building==c.building?1.:0.;
        json met=json::array(),unmet=json::array();
        if(!c.building.empty())(building?met:unmet).push_back("Prédio preferido: "+c.building);
        int matched=0;for(const auto& p:c.preferred){if(r.resources.count(p)){++matched;met.push_back("Recurso: "+p);}else unmet.push_back("Recurso: "+p);}
        double resources=c.preferred.empty()?1.:static_cast<double>(matched)/c.preferred.size(),stability=1.;
        std::set<std::string> previous;for(const auto& a:original)if(a.meeting==m.id)previous.insert(a.room);
        if(previous.empty())for(const auto& a:occupied){auto it=mi.find(a.meeting);if(it!=mi.end()&&meetings[it->second].classId==m.classId&&a.meeting!=m.id)previous.insert(a.room);}
        if(!previous.empty()){stability=previous.count(r.id)?1.:0.;(stability?met:unmet).push_back("Permanência na sala anterior/da turma");}
        double total=0.,score=0.;std::map<std::string,double> parts{{"capacity",capacity},{"building",building},{"resources",resources},{"stability",stability}};
        for(const auto& w:weights){total+=w.second;score+=w.second*parts.at(w.first);}score=std::round(10000.*score/total)/100.;
        std::ostringstream explanation;explanation<<"Sala válida: capacidade "<<r.capacity<<" para "<<c.size<<" estudantes; campus, recursos obrigatórios, acessibilidade, disponibilidade e sobreposições verificados. Adequação "<<score<<"/100. ";
        explanation<<"Preferências atendidas: "<<(met.empty()?"nenhuma preferência específica":met.dump(-1,' ',false,json::error_handler_t::replace))<<". ";
        explanation<<"Preferências não atendidas: "<<(unmet.empty()?"nenhuma":unmet.dump(-1,' ',false,json::error_handler_t::replace))<<".";
        json details={{"checks",{"capacity","campus","required_resources","accessibility","availability","room_overlap","teacher_overlap","class_overlap"}},{"components",parts},{"weights",weights},{"preferences_met",met},{"preferences_unmet",unmet},{"size_used",c.size},{"capacity",r.capacity}};
        return{roomIndex,score,explanation.str(),details};
    }
    std::vector<Candidate> candidates(const Meeting& m,const std::vector<Allocation>& occupied) {
        std::vector<Candidate> result;for(std::size_t i=0;i<rooms.size();++i)if(checks(m,rooms[i],occupied).empty())result.push_back(scored(m,static_cast<int>(i),occupied));
        std::sort(result.begin(),result.end(),[&](const Candidate& a,const Candidate& b){if(a.score!=b.score)return a.score>b.score;return rooms[a.room].id<rooms[b.room].id;});return result;
    }
    json pendingReasons(const Meeting& m) {
        json reasons=json::array();if(rooms.empty()){reasons.push_back("Nenhuma sala cadastrada.");return reasons;}
        std::map<std::string,std::pair<int,std::string>> counts;
        bool available=false;
        for(const auto& r:rooms){auto failures=checks(m,r,allocations);if(failures.empty())available=true;std::set<std::string> seen;for(const auto& f:failures)if(seen.insert(f.code).second){++counts[f.code].first;counts[f.code].second=f.message;}}
        if(available)reasons.push_back("Encontro sem alocação; existe ao menos uma sala válida disponível.");
        for(const auto& [code,value]:counts)reasons.push_back(value.second+" ["+std::to_string(value.first)+" de "+std::to_string(rooms.size())+" salas]");
        return reasons;
    }
public:
    explicit Engine(const json& input) {
        require(input.is_object(),"Entrada deve ser um objeto JSON.");
        for(const auto& j:array(input,"rooms",1000,true)) {
            require(j.is_object(),"rooms deve conter objetos.");Room r;
            r.id=id(j);r.name=str(j,"name",r.id);r.campus=id(j,"campus_id");r.building=str(j,"building_id");r.status=str(j,"status","active");r.capacity=integer(j,"capacity",0,1,100000);require(r.capacity>0,"Sala deve ter capacidade positiva.");r.accessible=boolean(j,"accessible");r.resources=strings(j,"resources");
            for(const auto& a:array(j,"available",1000))r.available.push_back(schedule(a,false));
            for(const auto& u:array(j,"unavailable",1000))r.unavailable.push_back(schedule(u,false));
            unique(ri,r.id,static_cast<int>(rooms.size()),"rooms");rooms.push_back(r);
        }
        for(const auto& j:array(input,"classes",2000,true)) {
            require(j.is_object(),"classes deve conter objetos.");Class c;
            c.id=id(j);c.campus=id(j,"campus_id");c.building=str(j,"preferred_building_id");c.status=str(j,"status","approved");
            c.active=c.status!="cancelled"&&c.status!="canceled"&&c.status!="closed"&&c.status!="cancelada"&&c.status!="encerrada";
            c.size=integer(j,"size_expected",0,1,100000);require(c.size>0,"Turma deve ter size_expected positivo.");
            if(j.contains("size_confirmed")&&!j.at("size_confirmed").is_null())c.size=integer(j,"size_confirmed",0,1,100000);
            c.accessibility=boolean(j,"needs_accessibility");c.required=strings(j,"required_resources");c.preferred=strings(j,"preferred_resources");c.teachers=strings(j,"teacher_emails",true);
            unique(ci,c.id,static_cast<int>(classes.size()),"classes");classes.push_back(c);
        }
        for(const auto& j:array(input,"meetings",4000,true)) {
            require(j.is_object(),"meetings deve conter objetos.");Meeting m;m.id=id(j);m.classId=id(j,"class_id");require(ci.count(m.classId),"Encontro referencia turma inexistente: "+m.classId);m.ci=ci.at(m.classId);m.when=schedule(j);
            unique(mi,m.id,static_cast<int>(meetings.size()),"meetings");meetings.push_back(m);
        }
        for(const auto& j:array(input,"allocations",8000)) {
            require(j.is_object(),"allocations deve conter objetos.");Allocation a;a.meeting=id(j,"meeting_id");a.room=id(j,"room_id");a.locked=boolean(j,"locked");a.value=j;
            a.value["locked"]=a.locked;a.value["source"]=str(j,"source","manual");original.push_back(a);
        }
        if(input.contains("weights")) {
            require(input.at("weights").is_object(),"weights deve ser objeto.");
            for(auto it=input.at("weights").begin();it!=input.at("weights").end();++it){require(weights.count(it.key()),"Peso desconhecido: "+it.key());require(it.value().is_number(),"Peso deve ser numérico.");double v=it.value().get<double>();require(std::isfinite(v)&&v>=0&&v<=1000000,"Peso deve ser finito, não negativo e até 1000000.");weights[it.key()]=v;}
        }
        double sum=0;for(const auto& w:weights)sum+=w.second;require(sum>0,"Pelo menos um peso deve ser positivo.");
        for(std::size_t i=0;i<meetings.size();++i)for(std::size_t j=i+1;j<meetings.size();++j) {
            const auto& a=meetings[i];const auto& b=meetings[j];if(!active(a)||!active(b)||!overlap(a.when,b.when))continue;
            auto record=[&](const char* code,const std::string& message){academic[a.id].push_back({code,message+" Encontro relacionado: "+b.id+"."});academic[b.id].push_back({code,message+" Encontro relacionado: "+a.id+"."});};
            if(a.classId==b.classId)record("CLASS_OVERLAP","A mesma turma possui encontros sobrepostos.");
            if(intersects(classes[a.ci].teachers,classes[b.ci].teachers))record("TEACHER_OVERLAP","Professor vinculado a encontros sobrepostos.");
        }
    }
    json run(const json& input) {
        auto started=std::chrono::steady_clock::now();auto mode=str(input,"mode","allocate");require(mode=="allocate"||mode=="validate"||mode=="suggest","mode deve ser allocate, validate ou suggest.");
        allocations=original;json suggestions=json::array();
        if(mode=="allocate") {
            std::set<std::string> selected;
            if(input.contains("selected_meeting_ids")){for(const auto& j:array(input,"selected_meeting_ids",4000)){require(j.is_string(),"selected_meeting_ids deve conter textos.");auto key=j.get<std::string>();require(mi.count(key),"Encontro selecionado inexistente: "+key);selected.insert(key);}}
            else for(const auto& m:meetings)if(active(m))selected.insert(m.id);
            allocations.erase(std::remove_if(allocations.begin(),allocations.end(),[&](const Allocation& a){return selected.count(a.meeting)&&!a.locked;}),allocations.end());
            std::set<std::string> fixed;for(const auto& a:allocations)fixed.insert(a.meeting);
            std::vector<std::pair<int,int>> order;
            for(std::size_t i=0;i<meetings.size();++i){const auto& m=meetings[i];if(!selected.count(m.id)||fixed.count(m.id)||!active(m))continue;int count=0;for(const auto& r:rooms)if(checks(m,r,{},false).empty())++count;order.push_back({count,static_cast<int>(i)});}
            std::sort(order.begin(),order.end(),[&](const auto& a,const auto& b){if(a.first!=b.first)return a.first<b.first;const auto& x=meetings[a.second];const auto& y=meetings[b.second];if(classes[x.ci].size!=classes[y.ci].size)return classes[x.ci].size>classes[y.ci].size;return x.id<y.id;});
            for(const auto& task:order){const auto& m=meetings[task.second];auto options=candidates(m,allocations);if(options.empty())continue;const auto& best=options.front();const auto& r=rooms[best.room];json value={{"meeting_id",m.id},{"room_id",r.id},{"source","automatic"},{"locked",false},{"score",best.score},{"explanation",best.explanation},{"details",best.details}};allocations.push_back({m.id,r.id,false,value});}
        }
        if(mode=="suggest") {
            auto key=id(input,"meeting_id");require(mi.count(key),"Encontro inexistente para sugestão: "+key);
            for(const auto& option:candidates(meetings[mi.at(key)],allocations))suggestions.push_back({{"room_id",rooms[option.room].id},{"score",option.score},{"explanation",option.explanation},{"details",option.details}});
        }
        json conflicts=json::array(),pending=json::array(),resultAllocations=json::array();std::set<std::string> assigned;
        auto conflict=[&](const std::string& meeting,const std::string& room,const std::string& code,const std::string& message){conflicts.push_back({{"meeting_id",meeting},{"room_id",room},{"code",code},{"message",message}});};
        for(const auto& a:allocations) {
            resultAllocations.push_back(a.value);
            if(!mi.count(a.meeting)){conflict(a.meeting,a.room,"UNKNOWN_MEETING","Alocação referencia encontro inexistente.");continue;}
            if(!assigned.insert(a.meeting).second)conflict(a.meeting,a.room,"DUPLICATE_ALLOCATION","Encontro possui mais de uma alocação; divisão deve ser cadastrada como turmas/encontros distintos.");
            if(!ri.count(a.room)){conflict(a.meeting,a.room,"UNKNOWN_ROOM","Alocação referencia sala inexistente.");continue;}
            auto failures=checks(meetings[mi.at(a.meeting)],rooms[ri.at(a.room)],allocations);
            for(const auto& r:failures)if(r.code!="TEACHER_OVERLAP"&&r.code!="CLASS_OVERLAP")conflict(a.meeting,a.room,r.code,r.message);
        }
        for(const auto& item:academic)for(const auto& r:item.second)conflict(item.first,"",r.code,r.message);
        std::set<std::string> classesWithMeetings;int activeMeetings=0,allocatedActive=0;
        for(const auto& m:meetings)if(active(m)){++activeMeetings;classesWithMeetings.insert(m.classId);if(!assigned.count(m.id))pending.push_back({{"meeting_id",m.id},{"reasons",pendingReasons(m)}});else ++allocatedActive;}
        for(const auto& c:classes)if(c.active&&!classesWithMeetings.count(c.id))conflict("","","CLASS_NO_MEETINGS","Turma ativa sem encontros cadastrados: "+c.id+".");
        json utilization=json::array();double occupiedPercent=0;int knownAllocated=0;
        for(const auto& r:rooms){int count=0,minutes=0;double ratio=0;std::set<std::string> counted;
            for(const auto& a:allocations)if(a.room==r.id&&mi.count(a.meeting)&&counted.insert(a.meeting).second){const auto& m=meetings[mi.at(a.meeting)];if(!active(m))continue;++count;minutes+=m.when.end-m.when.start;ratio+=100.*classes[m.ci].size/r.capacity;}
            knownAllocated+=count;occupiedPercent+=ratio;utilization.push_back({{"room_id",r.id},{"meetings",count},{"minutes_per_occurrence_sum",minutes},{"average_occupancy_percent",count?std::round(100.*ratio/count)/100.:0.}});
        }
        double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
        json statistics={{"rooms",rooms.size()},{"meetings",activeMeetings},{"allocated",allocatedActive},{"unallocated",pending.size()},{"conflicts",conflicts.size()},{"average_occupancy_percent",knownAllocated?std::round(100.*occupiedPercent/knownAllocated)/100.:0.},{"room_utilization",utilization},{"candidate_evaluations",evaluations},{"duration_ms",std::round(ms*100)/100.}};
        return{{"allocations",resultAllocations},{"unallocated",pending},{"conflicts",conflicts},{"suggestions",suggestions},{"valid",conflicts.empty()&&pending.empty()},{"statistics",statistics},{"weights",weights}};
    }
};
} // namespace
int main() {
    try {
        std::string input;input.reserve(32768);char buffer[8192];
        while(std::cin.read(buffer,sizeof(buffer))||std::cin.gcount()){input.append(buffer,static_cast<std::size_t>(std::cin.gcount()));require(input.size()<=MAX_INPUT,"Entrada excede limite de 8 MiB.");}
        auto document=json::parse(input,[](int depth,json::parse_event_t,json&){require(depth<=64,"JSON excede profundidade máxima de 64 níveis.");return true;});
        Engine engine(document);std::cout<<engine.run(document).dump(-1,' ',false,json::error_handler_t::replace)<<'\n';return 0;
    } catch(const std::exception& e) {
        json error={{"valid",false},{"errors",json::array({{{"code","INVALID_INPUT"},{"message",e.what()}}})},{"allocations",json::array()},{"unallocated",json::array()},{"conflicts",json::array()},{"suggestions",json::array()},{"statistics",json::object()}};
        std::cout<<error.dump(-1,' ',false,json::error_handler_t::replace)<<'\n';return 2;
    }
}
