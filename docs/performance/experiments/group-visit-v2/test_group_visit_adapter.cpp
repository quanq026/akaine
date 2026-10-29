#include <cassert>
#include <cstdio>
#include <map>
#include <vector>
#include "group_visit_adapter.h"
#include "group_visit_read_cache.h"
using namespace group_visit_adapter;
struct Reader {
    Address base = 0x1000000, next = 0x100000000ULL;
    std::map<Address, std::vector<unsigned char>> memory;
    unsigned writes = 0;
    unsigned raw_reads = 0;
    bool cache_enabled = true;
    group_visit_read_cache::Cache snapshots;
    Address allocate(size_t size) { const Address at = next; next += 0x2000; memory[at] = std::vector<unsigned char>(size); return at; }
    bool read(Address at, void* out, size_t size) {
        if (cache_enabled) return snapshots.read(at,out,size,[&](Address address,void* target,size_t bytes){return uncached(address,target,bytes);});
        return uncached(at,out,size);
    }
    bool uncached(Address at, void* out, size_t size) {
        ++raw_reads;
        auto found = memory.upper_bound(at); if (found == memory.begin()) return false; --found;
        if (at < found->first || at - found->first > found->second.size() || size > found->second.size() - (at - found->first)) return false;
        std::memcpy(out, found->second.data() + at - found->first, size); return true;
    }
    template<class T> void put(Address at, T value) {
        auto found = memory.upper_bound(at); assert(found != memory.begin()); --found;
        if (!(at >= found->first && at - found->first + sizeof(value) <= found->second.size()))
            std::fprintf(stderr, "fixture write bound at=%llx base=%llx size=%zu write=%zu\n", (unsigned long long)at, (unsigned long long)found->first, found->second.size(), sizeof(value));
        assert(at >= found->first && at - found->first + sizeof(value) <= found->second.size());
        std::memcpy(found->second.data() + at - found->first, &value, sizeof(value));
    }
    bool write_flags(Address at, uint32_t flags) { snapshots.clear(); ++writes; put(at, flags); return true; }
    bool members_hidden(const Address* values,unsigned count,Address expected) {
        for(unsigned i=0;i<count;++i){Address vt=0;uint8_t visible=1;
            if(!read(values[i],&vt,8)||!read(values[i]+0x1c1,&visible,1)||vt!=expected||visible)return false;}
        return true;
    }
    bool label_clean(Address at) {
        uint8_t flags[3]{};return read(at+0x344,&flags[0],1)&&read(at+0x2b4,&flags[1],1)
            &&read(at+0x5e3,&flags[2],1)&&!flags[0]&&!flags[1]&&!flags[2];
    }
    Address node(Address vt, Address parent, float width = 600, float height = 40) {
        const Address at = allocate(0x900); put(at, base + vt); put(at + 0x148, parent);
        put(at + 0x28, 1.f); put(at + 0x2c, 1.f); put(at + 0x30, 1.f); put(at + 0x34, 1.f);
        put(at + 0x5c, width); put(at + 0x60, height); put(at + 0x130, uint32_t(32));
        put(at + 0x1c0, uint8_t(1)); put(at + 0x1c1, uint8_t(1)); return at;
    }
    void children(Address parent, unsigned offset, std::initializer_list<Address> values) {
        Address vector = allocate(24), data = allocate(values.size() * 8 + 8);
        unsigned i = 0; for (Address item : values) put(data + i++ * 8, item);
        put(vector, data); put(vector + 8, data + values.size() * 8); put(vector + 16, data + values.size() * 8);
        put(parent + offset, vector);
    }
    void polygon(Address sprite, float y0 = 0, float y1 = 40) {
        struct Vertex { float x, y, z; uint32_t color; float u, v; };
        const Vertex vertices[] = {{0,y0,0,0,0,0},{1,y0,0,0,1,0},{1,y1,0,0,1,1},{0,y1,0,0,0,1}};
        Address data = allocate(sizeof(vertices)), indices = allocate(12);
        for (unsigned i=0;i<sizeof(vertices);++i) put(data+i, reinterpret_cast<const uint8_t*>(vertices)[i]);
        const uint16_t order[] = {0,1,2,0,2,3}; for(unsigned i=0;i<6;++i) put(indices+i*2,order[i]);
        put(sprite+0x468,data);put(sprite+0x470,indices);put(sprite+0x478,uint32_t(4));put(sprite+0x47c,uint32_t(6));
    }
};
struct Fixture {
    Reader r; Address director, scene, list, inner, group, renderer, matrix, button, scale9, internal, shadow, label, member1, member2;
    Fixture() {
        director=r.node(0x1b5eaf8,0);scene=r.node(0x1ad2260,0,1280,720);list=r.node(0x1b039c0,scene);inner=r.node(0x1af2d48,list);
        group=r.node(GROUP,inner);renderer=r.allocate(8);matrix=r.allocate(64);
        r.memory[r.base+0x1bee0a0]=std::vector<unsigned char>(8);r.put(r.base+0x1bee0a0,director);
        r.put(director+0x140,scene);r.put(director+0x198,renderer);r.put(scene+0x398,list);r.put(list+0x748,inner);
        r.put(inner+0x3c,-10000.f);r.put(group+0x3c,2000.f);r.put(group+0x5a1,uint8_t(1));r.put(group+0x5a2,uint8_t(1));r.put(group+0x5a4,40.f);
        for(unsigned i:{0u,5u,10u,15u})r.put(matrix+i*4,1.f);
        r.put(matrix+13*4,-10000.f);
        r.children(inner,0x140,{group});Address a=r.node(NODE,group),b=r.node(NODE,a);
        button=r.node(BUTTON,group,1,1);r.put(button+0x30,40.f);
        shadow=r.node(SPRITE,b);label=r.node(LABEL,b,200,20);Address label2=r.node(LABEL,b,100,20);
        r.children(group,0x140,{a,button});r.children(a,0x140,{b});r.children(b,0x140,{shadow,label,label2});
        r.put(group+0x550,a);r.put(group+0x560,button);r.put(group+0x578,b);r.put(group+0x580,shadow);r.put(group+0x590,label);r.put(group+0x598,label2);
        Address hidden1=r.node(SCALE9,button),hidden2=r.node(SCALE9,button);scale9=r.node(SCALE9,button,1,1);
        for(Address hidden:{hidden1,hidden2}) {r.put(hidden+0x1c1,uint8_t(0));r.put(hidden+0x130,uint32_t(51));r.put(hidden+0x330,uint8_t(1));}
        r.children(button,0x2a0,{hidden1,scale9,hidden2});internal=r.node(SPRITE,0,1,1);
        r.put(internal+0x130,uint32_t(51)); // Not visited: do not inspect its dirty/local transform.
        r.put(scale9+0x2d0,internal);r.put(scale9+0x2d8,uint8_t(1));r.polygon(internal,0,1);r.polygon(shadow);
        member1=r.node(0x1b177d0,group);member2=r.node(0x1b177d0,group);
        r.put(member1+0x1c1,uint8_t(0));r.put(member2+0x1c1,uint8_t(0));
        Address members=r.allocate(16);r.put(members,member1);r.put(members+8,member2);
        r.put(group+0x500,members);r.put(group+0x508,members+16);r.children(group,0x140,{a,button,member1,member2});
    }
    bool skip(uint32_t flags=0) { r.snapshots.clear(); return should_skip(r,group,renderer,matrix,flags); }
};
int main() {
    Fixture f; assert(f.skip() && !f.r.writes);
    assert(f.skip(1) && f.r.writes==1);uint32_t flags=0;assert(f.r.read(f.group+0x130,&flags,4)&&flags==0x30);
    assert(f.skip(0) && f.r.writes==1); // Parent settled; deferred refresh stays pending.
    f.r.put(f.group+0x3c,10000.f);assert(!f.skip(0)); // Reveal runs original visit with deferred0x10 still present.
    assert(f.r.read(f.group+0x130,&flags,4)&&flags==0x30); // Native ab8350 subsequently consumes/propagates it.
    assert(deferred_flags(0x20,2)==0x32 && deferred_flags(0x80,3)==0x92 && deferred_flags(0x30,0)==0x30);
    Fixture point;point.r.polygon(point.internal,200,300);assert(!point.skip()); // Actual Scale9 vertices reach viewport despite1x1contentsize.
    for(unsigned bad=0;bad<22;++bad) {
        Fixture x;
        if(bad==0)x.r.put(x.group+0x5a1,uint8_t(0));
        if(bad==1)x.r.put(x.button+0x503,uint8_t(1));
        if(bad==2)x.r.put(x.scale9+0x330,uint8_t(1));
        if(bad==3)x.r.put(x.scale9+0x2d8,uint8_t(0));
        if(bad==4)x.r.put(x.internal+0x478,uint32_t(65));
        if(bad==5)x.r.put(x.internal+0x47c,uint32_t(385));
        if(bad==6)x.r.put(x.shadow,x.r.base+0x12345);
        if(bad==7)x.r.put(x.label+0x344,uint8_t(1));
        if(bad==8)x.r.put(x.button+0x148,x.inner);
        if(bad==9)x.r.children(x.button,0x2a0,{x.scale9,x.scale9});
        if(bad==10)x.r.put(x.matrix+4,0.1f);
        if(bad==11)x.r.put(x.group+0x14,1.f);
        if(bad==12)x.r.put(x.internal+0x468,Address(0));
        if(bad==13)x.r.put(x.group+0x588,x.internal); // Declared visual not in visited header closure.
        if(bad==14)x.r.put(x.scene+0x398,x.inner);
        if(bad==15)x.r.put(x.label+0x2b4,uint8_t(1));
        if(bad==16)x.r.put(x.label+0x5e3,uint8_t(1));
        if(bad==17)x.r.put(x.button+0x128,x.internal);
        if(bad==18)x.r.put(x.member1+0x1c1,uint8_t(1));
        if(bad==19)x.r.put(x.member2,x.r.base+NODE);
        if(bad==21)x.r.put(x.label+0x130,uint32_t(0x80));
        assert(!x.skip(bad==20?4:0) && !x.r.writes);
    }
    Fixture dirty;dirty.r.put(dirty.label+0x130,uint32_t(51));assert(dirty.skip());
    bool forwarded=false;
    forward_native([&](Address self,Address renderer,Address transform,uint32_t flags,uint32_t extra) {
        assert(self==1&&renderer==2&&transform==3&&flags==0x1234&&extra==0xabcd);forwarded=true;
    },1,2,3,0x1234,0xabcd);
    assert(forwarded);
    Fixture measured;measured.r.cache_enabled=false;assert(measured.skip());const unsigned without=measured.r.raw_reads;
    measured.r.raw_reads=0;measured.r.cache_enabled=true;assert(measured.skip());const unsigned with=measured.r.raw_reads;
    assert(with<without);std::printf("Synthetic predicate copied-range calls without snapshot=%u with snapshot=%u\n",without,with);
    puts("PASS adapter exact closure, actualSprite/Scale9vertices, hidden-before-dirty prune, parentdirty skip-settle-reveal, original5arg contract inputs and strict fallbacks");
}
